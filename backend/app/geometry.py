"""Conservative mesh repair and real OCCT solid conversion; never fabricate CAD."""
import json
from pathlib import Path
import numpy as np
import trimesh
from .config import MAX_FACES


def region(points):
    points = np.asarray(points).reshape(-1, 3)
    if not len(points):
        return None
    return {'min': points.min(axis=0).tolist(), 'max': points.max(axis=0).tolist()}


def diagnose(mesh):
    edges = mesh.edges_sorted
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = unique[counts == 1]
    nonmanifold = unique[counts > 2]
    # Exact duplicate vertex merging is performed before diagnosis so STL's
    # independently stored triangle corners have meaningful adjacency.
    canonical = np.sort(mesh.faces, axis=1)
    _, first, inverse, frequencies = np.unique(canonical, axis=0, return_index=True,
                                               return_inverse=True, return_counts=True)
    duplicate = np.flatnonzero(frequencies[inverse] > 1)
    degenerate = np.flatnonzero(mesh.area_faces <= np.finfo(float).eps * max(mesh.scale**2, 1e-20))
    issues = []
    for name, ids, points in [
        ('boundary_edges', boundary, mesh.vertices[boundary]),
        ('non_manifold_edges', nonmanifold, mesh.vertices[nonmanifold]),
        ('duplicate_faces', duplicate, mesh.triangles[duplicate]),
        ('degenerate_faces', degenerate, mesh.triangles[degenerate]),
    ]:
        if len(ids):
            issues.append({'type': name, 'count': len(ids), 'bounds': region(points),
                           'indices': ids[:5000].tolist(), 'indices_truncated': len(ids) > 5000})
    return {'vertices': len(mesh.vertices), 'faces': len(mesh.faces),
            'bounds': mesh.bounds.tolist(), 'watertight': bool(mesh.is_watertight),
            'winding_consistent': bool(mesh.is_winding_consistent),
            'volume': float(abs(mesh.volume)), 'issues': issues,
            'mesh_self_intersections': 'not_checked'}


def load_mesh(path):
    mesh = trimesh.load(path, file_type='stl', force='mesh', process=False)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError('STL không chứa tam giác hợp lệ.')
    if len(mesh.faces) > MAX_FACES:
        raise ValueError(f'Lưới có {len(mesh.faces)} mặt; giới hạn bản đầu là {MAX_FACES}.')
    if not np.isfinite(mesh.vertices).all():
        raise ValueError('Tọa độ STL có NaN hoặc giá trị vô hạn.')
    # Merge ONLY bitwise-equal coordinates; no arbitrary geometric welding.
    vertices, inverse = np.unique(mesh.vertices, axis=0, return_inverse=True)
    mesh = trimesh.Trimesh(vertices=vertices, faces=inverse[mesh.faces], process=False)
    if mesh.scale <= 1e-12:
        raise ValueError('Kích thước lưới quá nhỏ hoặc bằng 0.')
    return mesh


def repair(mesh):
    fixed = mesh.copy()
    changes = []
    mask = fixed.nondegenerate_faces(height=max(mesh.scale * 1e-12, 1e-14))
    count = int((~mask).sum())
    if count:
        fixed.update_faces(mask)
        changes.append({'action': 'remove_degenerate_faces', 'count': count})
    mask = fixed.unique_faces()
    count = int((~mask).sum())
    if count:
        fixed.update_faces(mask)
        changes.append({'action': 'remove_duplicate_faces', 'count': count})
    if not len(fixed.faces):
        raise ValueError('Không còn mặt hợp lệ sau khi loại mặt lỗi.')
    old = fixed.faces.copy()
    trimesh.repair.fix_normals(fixed, multibody=True)
    changed = int(np.any(fixed.faces != old, axis=1).sum())
    if changed:
        changes.append({'action': 'orient_faces', 'count': changed})
    fixed.remove_unreferenced_vertices()
    return fixed, changes


def subshapes(shape, kind):
    from OCP.TopExp import TopExp_Explorer
    iterator = TopExp_Explorer(shape, kind)
    while iterator.More():
        yield iterator.Current()
        iterator.Next()


def shape_metrics(shape):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    prop = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, prop)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    b = box.Get()
    return {'valid': bool(BRepCheck_Analyzer(shape).IsValid()),
            'solids': sum(1 for _ in subshapes(shape, TopAbs_SOLID)),
            'faces': sum(1 for _ in subshapes(shape, TopAbs_FACE)),
            'volume': float(prop.Mass()), 'bounds': [list(b[:3]), list(b[3:])]}


def build_shape(mesh, tolerance, merge_planes):
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid)
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.gp import gp_Pnt
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError('Lưới còn hở hoặc phi đa tạp. Xem vị trí lỗi trong báo cáo; hệ thống không tự lấp lỗ.')
    components = list(mesh.split(only_watertight=False, repair=False))
    # Separate closed components may be assemblies, nested shells, or overlaps.
    # Do not guess cavity semantics: accept only clearly disjoint boxes.
    for i, a in enumerate(components):
        for b in components[i+1:]:
            if np.all(a.bounds[1] >= b.bounds[0] - tolerance) and np.all(b.bounds[1] >= a.bounds[0] - tolerance):
                raise ValueError('Các thành phần có vùng bao chồng nhau; cần xác định khối/lòng rỗng trước khi chuyển.')
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for part in components:
        if not part.is_watertight or not part.is_winding_consistent:
            raise ValueError('Lưới còn hở hoặc phi đa tạp. Xem vị trí lỗi trong báo cáo; hệ thống không tự lấp lỗ.')
        sewing = BRepBuilderAPI_Sewing(tolerance)
        for triangle in part.triangles:
            polygon = BRepBuilderAPI_MakePolygon()
            for p in triangle:
                polygon.Add(gp_Pnt(*map(float, p)))
            polygon.Close()
            sewing.Add(BRepBuilderAPI_MakeFace(polygon.Wire()).Face())
        sewing.Perform()
        shells = list(subshapes(sewing.SewedShape(), TopAbs_SHELL))
        if len(shells) != 1:
            raise ValueError('OCCT không dựng được một shell kín cho thành phần lưới.')
        solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shells[0])).Solid()
        if shape_metrics(solid)['volume'] < 0:
            solid.Reverse()
        if merge_planes:
            unify = ShapeUpgrade_UnifySameDomain(solid, True, True, False)
            # Strict thresholds: merge coplanar faces, never smooth curved facets.
            unify.SetLinearTolerance(min(tolerance, 1e-7))
            unify.SetAngularTolerance(1e-10)
            unify.Build()
            solid = unify.Shape()
        builder.Add(compound, solid)
    return compound, len(components)


def export_preview(shape, path, tolerance):
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    BRepMesh_IncrementalMesh(shape, max(tolerance, 0.01), False, 0.2, False).Perform()
    triangles = []
    for item in subshapes(shape, TopAbs_FACE):
        face = TopoDS.Face_s(item)
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)
        if triangulation is None:
            continue
        for j in range(1, triangulation.NbTriangles()+1):
            ids = list(triangulation.Triangle(j).Get())
            if face.Orientation() == TopAbs_REVERSED:
                ids.reverse()
            triangles.append([list(triangulation.Node(k).Transformed(loc.Transformation()).Coord()) for k in ids])
    points = np.asarray(triangles)
    preview = trimesh.Trimesh(vertices=points.reshape(-1, 3),
                              faces=np.arange(points.size//3).reshape(-1, 3), process=False)
    preview.export(path, file_type='stl')


def convert(source: Path, output_dir: Path, unit='mm', merge_planes=True, progress=lambda *x: None):
    from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    import OCP
    report = {'engine': f'OCCT {OCP.__version__}', 'unit': unit,
              'mode': 'planar_merge' if merge_planes else 'faceted', 'success': False,
              'limitations': ['Không khớp tự động mặt trụ/cầu/NURBS; không dùng AI trong bản này.',
                              'Không tự vá lỗ, làm mịn hoặc thay đổi tỷ lệ.',
                              'Tự giao của mesh chưa được kiểm tra đầy đủ; CAD được kiểm tra BRepCheck.']}
    step = output_dir / 'result.step'
    try:
        progress(15, 'Đang phân tích lưới và định vị lỗi')
        mesh = load_mesh(source)
        report['before'] = diagnose(mesh)
        fixed, changes = repair(mesh)
        report['repairs'] = changes
        report['after'] = diagnose(fixed)
        fixed.export(output_dir / 'repaired.stl')
        tolerance = max(1e-7, mesh.scale * 1e-9)
        report['sewing_tolerance'] = tolerance
        progress(40, 'Đang khâu shell và dựng solid CAD')
        shape, components = build_shape(fixed, tolerance, merge_planes)
        before = shape_metrics(shape)
        bound_error = float(np.max(np.abs(np.asarray(before['bounds']) - fixed.bounds)))
        volume_error = abs(before['volume'] - abs(fixed.volume)) / max(abs(fixed.volume), 1e-30)
        if not before['valid'] or before['solids'] != components or before['volume'] <= 0:
            raise ValueError('Solid CAD không đạt kiểm tra hợp lệ/thể tích/số thành phần.')
        if bound_error > tolerance * 20 or volume_error > 1e-5:
            raise ValueError('Sai lệch kích thước hoặc thể tích sau dựng CAD vượt giới hạn.')
        progress(75, 'Đang xuất STEP và nhập lại để xác minh')
        STEPControl_Writer()  # Initialize OCCT's STEP parameter registry.
        Interface_Static.SetCVal_s('write.step.schema', 'AP214IS')
        # Numeric coordinates are unchanged; STEP receives the selected unit.
        occ_unit = {'mm': 'MM', 'cm': 'CM', 'm': 'M', 'inch': 'INCH'}[unit]
        Interface_Static.SetCVal_s('write.step.unit', occ_unit)
        Interface_Static.SetCVal_s('xstep.cascade.unit', 'MM')
        writer = STEPControl_Writer()
        unit_mm = {'mm': 1.0, 'cm': 10.0, 'm': 1000.0, 'inch': 25.4}[unit]
        writer.Model().SetLocalLengthUnit(unit_mm)
        writer.Model().SetWriteLengthUnit(unit_mm)
        if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone or writer.Write(str(step)) != IFSelect_RetDone:
            raise ValueError('OCCT không xuất được STEP.')
        reader = STEPControl_Reader()
        if reader.ReadFile(str(step)) != IFSelect_RetDone:
            raise ValueError('Không đọc lại được STEP vừa xuất.')
        reader.SetSystemLengthUnit(unit_mm)
        reader.TransferRoots()
        reimported = reader.OneShape()
        after = shape_metrics(reimported)
        if not after['valid'] or after['solids'] != components or after['volume'] <= 0:
            raise ValueError('STEP sau nhập lại không còn là solid hợp lệ.')
        if np.max(np.abs(np.asarray(after['bounds']) - np.asarray(before['bounds']))) > tolerance * 20:
            raise ValueError('Kích thước STEP sau nhập lại vượt dung sai.')
        if abs(after['volume'] - before['volume']) / before['volume'] > 1e-5:
            raise ValueError('Thể tích STEP sau nhập lại vượt dung sai.')
        report['verification'] = {'before_export': before, 'after_reimport': after,
                                  'bounds_max_error': bound_error, 'relative_volume_error': volume_error,
                                  'surface_deviation': 'not_sampled; only coplanar faces are merged'}
        report['output_geometry'] = 'planar_brep; curved surfaces remain faceted'
        export_preview(reimported, output_dir / 'preview.stl', tolerance)
        report['success'] = True
    except Exception as exc:
        step.unlink(missing_ok=True)
        report['error'] = str(exc)
    finally:
        (output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return report
