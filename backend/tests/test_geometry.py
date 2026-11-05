from pathlib import Path
import numpy as np
import pytest
import trimesh
from app.geometry import convert


def run(tmp_path, mesh, **kwargs):
    source = tmp_path / 'source.stl'
    mesh.export(source)
    return convert(source, tmp_path, **kwargs)


def test_cube_has_six_faces_and_step_roundtrip(tmp_path):
    report = run(tmp_path, trimesh.creation.box(extents=[20, 30, 12]))
    assert report['success'], report
    result = report['verification']['after_reimport']
    assert result['solids'] == 1 and result['faces'] == 6
    assert result['volume'] == pytest.approx(7200)
    assert (tmp_path / 'result.step').read_text().startswith('ISO-10303-21;')


@pytest.mark.parametrize('unit', ['mm', 'cm', 'm', 'inch'])
def test_units_do_not_scale_coordinates(tmp_path, unit):
    report = run(tmp_path, trimesh.creation.box(extents=[2, 4, 6]), unit=unit)
    assert report['success'], report
    metrics = report['verification']['after_reimport']
    assert metrics['volume'] == pytest.approx(48, rel=1e-7)
    assert np.subtract(*reversed(metrics['bounds'])) == pytest.approx([2, 4, 6])
    # Independent consumer reads STEP in mm to verify its physical unit, not
    # only the converter's own report normalization.
    from OCP.STEPControl import STEPControl_Reader
    from app.geometry import shape_metrics
    reader = STEPControl_Reader()
    reader.ReadFile(str(tmp_path / 'result.step'))
    reader.SetSystemLengthUnit(1.0)
    reader.TransferRoots()
    mm = shape_metrics(reader.OneShape())
    factor = {'mm': 1, 'cm': 10, 'm': 1000, 'inch': 25.4}[unit]
    assert np.subtract(*reversed(mm['bounds'])) == pytest.approx(np.array([2, 4, 6])*factor)


def test_open_mesh_reports_error_location_and_no_step(tmp_path):
    mesh = trimesh.creation.box()
    mesh.update_faces(np.arange(len(mesh.faces)-1))
    report = run(tmp_path, mesh)
    assert not report['success']
    issue = next(i for i in report['after']['issues'] if i['type'] == 'boundary_edges')
    assert issue['count'] == 3 and issue['bounds'] is not None
    assert not (tmp_path / 'result.step').exists()


def test_duplicate_and_flipped_faces_are_repaired(tmp_path):
    mesh = trimesh.creation.box()
    faces = np.vstack([mesh.faces, mesh.faces[:1]])
    faces[3] = faces[3][::-1]
    mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=faces, process=False)
    report = run(tmp_path, mesh)
    assert report['success'], report
    assert any(r['action'] == 'remove_duplicate_faces' for r in report['repairs'])
    assert report['after']['faces'] == 12


def test_disjoint_parts_remain_two_solids(tmp_path):
    a, b = trimesh.creation.box(), trimesh.creation.box()
    b.apply_translation([3, 0, 0])
    report = run(tmp_path, a+b)
    assert report['success'], report
    assert report['verification']['after_reimport']['solids'] == 2


def test_overlapping_parts_are_rejected(tmp_path):
    a, b = trimesh.creation.box(), trimesh.creation.box()
    b.apply_translation([0.4, 0.3, 0.2])
    report = run(tmp_path, a+b)
    assert not report['success']
    assert not (tmp_path / 'result.step').exists()


def test_curved_facets_are_not_claimed_as_cylinder(tmp_path):
    report = run(tmp_path, trimesh.creation.cylinder(radius=5, height=10, sections=24))
    assert report['success'], report
    assert report['verification']['after_reimport']['faces'] == 26
    assert 'faceted' in report['output_geometry']


def test_faceted_mode_preserves_cube_triangles(tmp_path):
    report = run(tmp_path, trimesh.creation.box(), merge_planes=False)
    assert report['success'], report
    assert report['verification']['after_reimport']['faces'] == 12


def test_bad_stl_does_not_create_output(tmp_path):
    source = tmp_path / 'source.stl'
    source.write_bytes(b'not an stl')
    report = convert(source, tmp_path)
    assert not report['success'] and 'error' in report
    assert (tmp_path / 'report.json').exists()
    assert not (tmp_path / 'result.step').exists()
