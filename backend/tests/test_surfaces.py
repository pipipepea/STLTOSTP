import numpy as np
import pytest
import trimesh
from OCP.STEPControl import STEPControl_Reader
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from app.geometry import convert, shape_metrics, subshapes
from app.surfaces import reconstruct, surface_types


def converted(tmp_path, mesh, **options):
    mesh.export(tmp_path/'source.stl')
    return convert(tmp_path/'source.stl', tmp_path, curve_mode='auto', **options)


def read_step(path, unit=1):
    reader = STEPControl_Reader()
    reader.ReadFile(str(path))
    reader.SetSystemLengthUnit(unit)
    reader.TransferRoots()
    return reader.OneShape()


@pytest.mark.parametrize('kind,expected', [
    ('cylinder', {'plane': 2, 'cylinder': 1}),
    ('cone', {'plane': 1, 'cone': 1}),
    ('sphere', {'sphere': 1}),
    ('torus', {'torus': 1}),
    ('tube', {'plane': 2, 'cylinder': 2}),
    ('stepped_chamfer', {'plane': 3, 'cylinder': 2, 'cone': 1}),
])
def test_exact_analytic_surface_types_after_step_import(tmp_path, kind, expected):
    meshes = {
        'cylinder': lambda: trimesh.creation.cylinder(radius=5, height=12, sections=64),
        'cone': lambda: trimesh.creation.cone(radius=5, height=12, sections=64),
        'sphere': lambda: trimesh.creation.icosphere(subdivisions=3, radius=5),
        'torus': lambda: trimesh.creation.torus(major_radius=8, minor_radius=2, major_sections=64, minor_sections=48),
        'tube': lambda: trimesh.creation.revolve([[3, 0], [5, 0], [5, 12], [3, 12], [3, 0]], sections=64),
        'stepped_chamfer': lambda: trimesh.creation.revolve([[0, 0], [5, 0], [5, 3], [4, 4], [3, 4], [3, 12], [0, 12]], sections=64),
    }
    report = converted(tmp_path, meshes[kind]())
    assert report['success'], report
    assert report['curve_reconstruction']['accepted_components'] == 1
    shape = read_step(tmp_path/'result.step')
    assert surface_types(shape) == expected
    assert report['surface_types'] == expected
    detail = report['curve_reconstruction']['components'][0]
    assert detail['mesh_to_cad']['max'] <= .05
    assert detail['cad_to_mesh']['max'] <= .05
    assert detail['relative_volume_change'] <= .02


def test_rotated_translated_cylinder_radius_and_axis_are_preserved(tmp_path):
    mesh = trimesh.creation.cylinder(radius=5, height=12, sections=64)
    transform = trimesh.transformations.rotation_matrix(.73, [1, 2, 3])
    transform[:3, 3] = [51, -23, 19]
    mesh.apply_transform(transform)
    report = converted(tmp_path, mesh)
    assert report['success'], report
    assert report['surface_types'] == {'plane': 2, 'cylinder': 1}
    shape = read_step(tmp_path/'result.step')
    cylinders = [BRepAdaptor_Surface(TopoDS.Face_s(f)).Cylinder() for f in subshapes(shape, TopAbs_FACE)
                 if BRepAdaptor_Surface(TopoDS.Face_s(f)).GetType().name == 'GeomAbs_Cylinder']
    assert cylinders[0].Radius() == pytest.approx(5, abs=2e-5)
    actual = np.array(cylinders[0].Axis().Direction().Coord())
    assert abs(actual @ transform[:3, 2]) == pytest.approx(1, abs=1e-8)


@pytest.mark.parametrize('unit,factor', [('mm', 1), ('cm', 10), ('m', 1000), ('inch', 25.4)])
def test_curved_step_physical_units(tmp_path, unit, factor):
    report = converted(tmp_path, trimesh.creation.cylinder(radius=5, height=12, sections=64), unit=unit)
    assert report['success'], report
    shape = read_step(tmp_path/'result.step', 1)
    assert shape_metrics(shape)['volume'] == pytest.approx(np.pi*25*12*factor**3, rel=1e-6)


def test_strict_tolerance_rejects_fit_but_auto_retains_facets(tmp_path):
    mesh = trimesh.creation.cylinder(radius=5, height=12, sections=24)
    report = converted(tmp_path, mesh, fit_tolerance=.0001)
    assert report['success']
    assert report['curve_reconstruction']['accepted_components'] == 0
    assert report['surface_types'] == {'plane': 26}
    assert not report['curve_reconstruction']['components'][0]['accepted']


def test_required_fit_never_silently_returns_facets(tmp_path):
    mesh = trimesh.creation.box(extents=[10, 10, 10])
    mesh.export(tmp_path/'source.stl')
    report = convert(tmp_path/'source.stl', tmp_path, curve_mode='required')
    assert not report['success']
    assert 'curve_reconstruction' in report
    assert not (tmp_path/'result.step').exists()


def test_volume_limit_independently_blocks_reconstruction(tmp_path):
    report = converted(tmp_path, trimesh.creation.cylinder(radius=5, height=12, sections=64),
                       max_volume_change=.00001)
    assert report['success']
    assert report['curve_reconstruction']['accepted_components'] == 0
    attempts = report['curve_reconstruction']['components'][0]['attempts']
    assert any('Volume change' in a['reason'] for a in attempts)


def test_mixed_assembly_keeps_unsupported_part_and_reports_it(tmp_path):
    cylinder = trimesh.creation.cylinder(radius=5, height=12, sections=64)
    box = trimesh.creation.box(extents=[4, 4, 4])
    box.apply_translation([20, 0, 0])
    report = converted(tmp_path, cylinder+box)
    assert report['success'], report
    assert report['verification']['after_reimport']['solids'] == 2
    assert report['surface_types'] == {'plane': 8, 'cylinder': 1}
    assert report['curve_reconstruction']['accepted_components'] == 1
    assert len(report['curve_reconstruction']['components']) == 2


def test_asymmetric_feature_is_not_erased():
    mesh = trimesh.creation.cylinder(radius=5, height=12, sections=64)
    mesh.vertices[np.argmax(mesh.vertices[:, 0]), 0] += .4
    shape, detail = reconstruct(mesh, .03, .02)
    assert shape is None and not detail['accepted']


def test_reverse_direction_rejects_missing_surface_coverage():
    from app.surfaces import rotational_candidate, validate_candidate
    # Exercise the reverse gate independently of the forward/volume gates.
    mesh = trimesh.creation.cylinder(radius=5, height=12, sections=64)
    candidate = rotational_candidate(mesh, mesh.vertices.mean(axis=0), np.array([0, 0, 1.]), .05)
    candidate.distance = lambda points: np.zeros(len(points))
    candidate.samples = np.array([[20., 0, 0]])
    report = validate_candidate(mesh, candidate, .05, .02)
    assert not report['accepted']
    assert report['mesh_to_cad']['max'] == 0
    assert report['cad_to_mesh']['max'] > .05
    assert 'CAD-to-mesh' in report['reason']


def test_invalid_tolerances_do_not_export(tmp_path):
    mesh = trimesh.creation.cylinder(radius=5, height=12, sections=64)
    report = converted(tmp_path, mesh, fit_tolerance=float('nan'))
    assert not report['success']
    assert not (tmp_path/'result.step').exists()


@pytest.mark.parametrize('rotated', [False, True])
def test_extruded_plate_preserves_multiple_offset_circular_holes(tmp_path, rotated):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    from app.geometry import export_preview, load_mesh
    design = BRepPrimAPI_MakeBox(20., 16., 4.).Shape()
    for x in [6., 14.]:
        tool = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, 8., 0.), gp_Dir(0, 0, 1)), 2., 4.).Shape()
        design = BRepAlgoAPI_Cut(design, tool).Shape()
    export_preview(design, tmp_path/'source.stl', .01)
    if rotated:
        mesh = load_mesh(tmp_path/'source.stl')
        transform = trimesh.transformations.rotation_matrix(.48, [2, -1, 3])
        transform[:3, 3] = [42, 19, -5]
        mesh.apply_transform(transform)
        mesh.export(tmp_path/'source.stl')
    report = convert(tmp_path/'source.stl', tmp_path, curve_mode='auto')
    assert report['success'], report
    assert report['surface_types'] == {'plane': 6, 'cylinder': 2}
    detail = report['curve_reconstruction']['components'][0]
    assert detail['parameters']['type'] == 'extrusion'
    assert detail['parameters']['holes_preserved'] == 2
    assert detail['cad_to_mesh']['max'] <= .05


def rounded_rectangle_prism():
    # Independent convex fan triangulation of a rounded rectangle contour.
    outline = []
    for x, y, angle in [(6, 4, 0), (-6, 4, np.pi/2), (-6, -4, np.pi), (6, -4, 3*np.pi/2)]:
        for theta in np.linspace(angle, angle+np.pi/2, 17):
            outline.append([x+2*np.cos(theta), y+2*np.sin(theta)])
    n = len(outline)
    vertices = [[0, 0, 0], [0, 0, 3]]
    for x, y in outline:
        vertices.extend([[x, y, 0], [x, y, 3]])
    faces = []
    for i in range(n):
        a, b = 2+2*i, 2+2*((i+1) % n)
        faces.extend([[0, b, a], [1, a+1, b+1], [a, b, b+1], [a, b+1, a+1]])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


def test_rounded_extruded_outline_becomes_cylindrical_corner_patches(tmp_path):
    report = converted(tmp_path, rounded_rectangle_prism())
    assert report['success'], report
    assert report['surface_types'] == {'plane': 6, 'cylinder': 4}
    assert report['curve_reconstruction']['components'][0]['parameters']['type'] == 'extrusion'


def test_varying_extrusion_cross_section_is_not_flattened(tmp_path):
    mesh = rounded_rectangle_prism()
    mesh.vertices[mesh.vertices[:, 2] > 2, :2] *= .8
    report = converted(tmp_path, mesh)
    assert report['success'], report
    assert report['curve_reconstruction']['accepted_components'] == 0
