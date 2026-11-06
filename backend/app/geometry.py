"""Conservative mesh repair and real OCCT solid conversion; never fabricate CAD."""
import json
from pathlib import Path
import numpy as np
import trimesh
from .config import MAX_FACES, MAX_INPUT_FACES


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
    if len(mesh.faces) > MAX_INPUT_FACES:
        raise ValueError(f'Lưới có {len(mesh.faces)} mặt; giới hạn đọc STL là {MAX_INPUT_FACES}.')
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


def build_shape(mesh, tolerance, merge_planes, *, curve_mode='off', fit_tolerance=.05,
                max_volume_change=.02, curve_components=None):
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
    for part_id, part in enumerate(components):
        if not part.is_watertight or not part.is_winding_consistent:
            raise ValueError('Lưới còn hở hoặc phi đa tạp. Xem vị trí lỗi trong báo cáo; hệ thống không tự lấp lỗ.')
        if curve_mode != 'off':
            from .surfaces import reconstruct, surface_types
            fitted, detail = reconstruct(part, fit_tolerance, max_volume_change)
            detail.update(component=part_id, source_faces=len(part.faces), bounds=part.bounds.tolist())
            if fitted is not None:
                detail['surface_types'] = surface_types(fitted)
            if curve_components is not None:
                curve_components.append(detail)
            if fitted is not None:
                builder.Add(compound, fitted)
                continue
            if curve_mode == 'required':
                raise ValueError(f'Thành phần {part_id}: không khớp được bề mặt cong trong dung sai. Xem báo cáo thử khớp.')
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
    BRepMesh_IncrementalMesh(shape, max(tolerance, 1e-7), False, 0.2, False).Perform()
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


def convert(source: Path, output_dir: Path, unit='mm', merge_planes=True, progress=lambda *x: None,
            *, curve_mode='off', fit_tolerance=.05, max_volume_change=.02,
            simplify_mesh=False, target_faces=None, simplify_tolerance=.05):
    from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    import OCP
    report = {'engine': f'OCCT {OCP.__version__}', 'unit': unit,
              'mode': 'planar_merge' if merge_planes else 'faceted', 'success': False,
              'limitations': ['Phục dựng cầu, xuyến, biên dạng tròn xoay và khối đùn sâu không đổi với cung tròn/lỗ tròn; chưa khớp NURBS tự do hay mọi mảnh cong tùy ý.',
                              'Không tự vá lỗ, làm mịn hoặc thay đổi tỷ lệ.',
                              'Sai lệch bề mặt được đo bằng lấy mẫu, không phải bảo đảm Hausdorff liên tục.',
                              'Tự giao của mesh chưa được kiểm tra đầy đủ; CAD được kiểm tra BRepCheck.']}
    step = output_dir / 'result.step'
    try:
        target_faces = min(25000, MAX_FACES) if target_faces is None else target_faces
        if isinstance(target_faces, bool) or not isinstance(target_faces, int) or not 4 <= target_faces <= MAX_FACES:
            raise ValueError(f'Số mặt đích phải là số nguyên từ 4 đến {MAX_FACES}.')
        if not np.isfinite(simplify_tolerance) or simplify_tolerance <= 0:
            raise ValueError('Dung sai giảm lưới phải là số hữu hạn lớn hơn 0.')
        if curve_mode not in {'off', 'auto', 'required'}:
            raise ValueError('Chế độ phục dựng bề mặt không hợp lệ.')
        if not np.isfinite(fit_tolerance) or fit_tolerance <= 0:
            raise ValueError('Dung sai bề mặt phải là số hữu hạn lớn hơn 0.')
        if not np.isfinite(max_volume_change) or not 0 < max_volume_change <= .05:
            raise ValueError('Giới hạn thay đổi thể tích phải lớn hơn 0 và không quá 5%.')
        progress(15, 'Đang phân tích lưới và định vị lỗi')
        mesh = load_mesh(source)
        report['before'] = diagnose(mesh)
        fixed, changes = repair(mesh)
        report['repairs'] = changes
        report['after'] = diagnose(fixed)
        fixed.export(output_dir / 'repaired.stl')
        reference = fixed
        reduction = report['simplification'] = {'requested': simplify_mesh, 'applied': False}
        if simplify_mesh:
            from .simplification import simplify
            progress(25, 'Đang giảm lưới và kiểm tra sai lệch, topology, cạnh sắc')
            fixed = simplify(reference, target_faces, simplify_tolerance, reduction)
            if reduction['applied']:
                fixed.export(output_dir / 'simplified.stl')
        if len(fixed.faces) > MAX_FACES:
            raise ValueError(f'Lưới có {len(fixed.faces)} mặt; giới hạn dựng CAD là {MAX_FACES}. Bật Giảm lưới trước chuyển đổi để tiếp tục.')
        report['conversion_mesh'] = diagnose(fixed)
        tolerance = max(1e-7, mesh.scale * 1e-9)
        report['sewing_tolerance'] = tolerance
        progress(40, 'Đang khớp bề mặt cong và đo sai lệch' if curve_mode != 'off' else 'Đang khâu shell và dựng solid CAD')
        curve_components = []
        report['curve_reconstruction'] = {'mode': curve_mode, 'fit_tolerance': fit_tolerance,
                                           'max_volume_change': max_volume_change,
                                           'reference_mesh': 'simplified' if reduction['applied'] else 'repaired_original',
                                           'components': curve_components}
        shape, components = build_shape(fixed, tolerance, merge_planes, curve_mode=curve_mode,
                                         fit_tolerance=fit_tolerance, max_volume_change=max_volume_change,
                                         curve_components=curve_components)
        reconstructed = sum(bool(c['accepted']) for c in curve_components)
        report['curve_reconstruction']['accepted_components'] = reconstructed
        before = shape_metrics(shape)
        bound_error = float(np.max(np.abs(np.asarray(before['bounds']) - fixed.bounds)))
        volume_error = abs(before['volume'] - abs(fixed.volume)) / max(abs(fixed.volume), 1e-30)
        if not before['valid'] or before['solids'] != components or before['volume'] <= 0:
            raise ValueError('Solid CAD không đạt kiểm tra hợp lệ/thể tích/số thành phần.')
        bound_limit = fit_tolerance if reconstructed else tolerance*20
        volume_limit = max_volume_change if reconstructed else 1e-5
        if bound_error > bound_limit or volume_error > volume_limit:
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
        from .surfaces import surface_types
        report['surface_types'] = surface_types(reimported)
        if report['surface_types'] != surface_types(shape):
            raise ValueError('Loại bề mặt thay đổi sau khi nhập lại STEP.')
        if not after['valid'] or after['solids'] != components or after['volume'] <= 0:
            raise ValueError('STEP sau nhập lại không còn là solid hợp lệ.')
        if np.max(np.abs(np.asarray(after['bounds']) - np.asarray(before['bounds']))) > tolerance * 20:
            raise ValueError('Kích thước STEP sau nhập lại vượt dung sai.')
        if abs(after['volume'] - before['volume']) / before['volume'] > 1e-5:
            raise ValueError('Thể tích STEP sau nhập lại vượt dung sai.')
        if reconstructed:
            from .surfaces import verify_step_distances
            report['curve_reconstruction']['reimported_step_distances'] = verify_step_distances(
                fixed, reimported, curve_components, fit_tolerance)
        report['verification'] = {'before_export': before, 'after_reimport': after,
                                  'bounds_max_error': bound_error, 'relative_volume_error': volume_error,
                                  'bounds_limit': bound_limit, 'relative_volume_limit': volume_limit,
                                  'surface_deviation': 'see curve_reconstruction.components; sampled bidirectional checks' if reconstructed else 'not_sampled; only coplanar faces are merged'}
        report['output_geometry'] = ('analytic_curved_brep_with_possible_faceted_components' if reconstructed
                                      else 'planar_brep; curved surfaces remain faceted')
        report['mode'] = 'analytic_curves' if reconstructed else report['mode']
        preview_tolerance = min(.01, fit_tolerance*.2) if reconstructed else tolerance
        export_preview(reimported, output_dir / 'preview.stl', preview_tolerance)
        if reduction['applied']:
            # Validate the combined reduction + CAD fitting path against the
            # repaired original, so error from the two stages is not hidden.
            from .simplification import compare_meshes
            preview = trimesh.load(
                output_dir / 'preview.stl', file_type='stl', force='mesh', process=False)
            budget = simplify_tolerance+(fit_tolerance if reconstructed else tolerance*20)
            check = compare_meshes(reference, preview, budget+max(preview_tolerance, 1e-7))
            check['reduction_and_fit_budget'] = budget
            check['preview_deflection_budget'] = max(preview_tolerance, 1e-7)
            check['measurement'] = 'original_repaired_mesh_vs_reimported_STEP_tessellation_samples'
            report['verification']['original_surface_deviation'] = check
            combined_volume_limit = (1.01*(1+max_volume_change)-1) if reconstructed else .01002
            original_volume_change = abs(before['volume']-abs(reference.volume))/max(abs(reference.volume), 1e-30)
            report['verification']['original_relative_volume_change'] = float(original_volume_change)
            report['verification']['original_relative_volume_limit'] = combined_volume_limit
            if not check['passed'] or original_volume_change > combined_volume_limit:
                raise ValueError('Tổng sai lệch STEP so với lưới gốc sau giảm lưới và phục dựng vượt giới hạn.')
        report['success'] = True
    except Exception as exc:
        step.unlink(missing_ok=True)
        report['error'] = str(exc)
        if report.get('simplification', {}).get('requested') and not report['simplification'].get('accepted'):
            report['simplification']['rejection_reason'] = str(exc)
    finally:
        (output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return report
