"""Opt-in topology-preserving decimation with independent sampled geometry gates."""
import numpy as np
import trimesh


def probes(mesh, limit=12000):
    from .surfaces import mesh_probes
    points = mesh_probes(mesh)
    if len(points) > limit:
        points = points[np.linspace(0, len(points)-1, limit, dtype=int)]
    # Add deterministic area-weighted samples, complementing index-based probes.
    extra, _ = trimesh.sample.sample_surface(mesh, 2000, seed=2026)
    return np.vstack([points, extra])


def distances_to_mesh(mesh, points):
    distances = []
    for start in range(0, len(points), 128):
        _, values, _ = trimesh.proximity.closest_point(mesh, points[start:start+128])
        distances.append(values)
    return np.concatenate(distances)


def compare_meshes(original, reduced, tolerance):
    from .surfaces import summary
    forward_points, reverse_points = probes(original), probes(reduced)
    forward = summary(distances_to_mesh(reduced, forward_points), forward_points)
    reverse = summary(distances_to_mesh(original, reverse_points), reverse_points)
    return {'source_to_result': forward, 'result_to_source': reverse,
            'tolerance': float(tolerance),
            'passed': max(forward['max'], reverse['max']) <= tolerance,
            'measurement': 'sampled_point_to_triangle_not_certified_Hausdorff'}


def sharp_segments(mesh):
    mask = mesh.face_adjacency_angles >= np.deg2rad(30)
    return mesh.vertices[mesh.face_adjacency_edges[mask]]


def feature_distance(source_segments, target_segments, tolerance):
    if not len(source_segments):
        return {'passed': True, 'max': 0., 'samples': 0}
    if not len(target_segments):
        return {'passed': False, 'reason': 'Sharp edges disappeared', 'samples': 0}
    from rtree import index
    properties = index.Property()
    properties.dimension = 3
    tree = index.Index(properties=properties)
    for i, segment in enumerate(target_segments):
        tree.insert(i, np.r_[segment.min(axis=0), segment.max(axis=0)])
    # Keep bounded cost; inspect endpoints and midpoints on selected feature edges.
    chosen = source_segments[np.linspace(0, len(source_segments)-1, min(2000, len(source_segments)), dtype=int)]
    points = np.concatenate([chosen[:, 0], chosen[:, 1], chosen.mean(axis=1)])
    worst = 0.
    for point in points:
        ids = list(tree.intersection(np.r_[point-tolerance, point+tolerance]))
        if not ids:
            return {'passed': False, 'reason': 'Sharp edge moved beyond tolerance',
                    'worst_point': point.tolist(), 'samples': len(points)}
        best = np.inf
        for start in range(0, len(ids), 1024):
            edges = target_segments[ids[start:start+1024]]
            a, d = edges[:, 0], edges[:, 1]-edges[:, 0]
            t = np.clip(np.sum((point-a)*d, axis=1)/np.maximum(np.sum(d*d, axis=1), 1e-30), 0, 1)
            best = min(best, float(np.linalg.norm(point-a-t[:, None]*d, axis=1).min()))
        worst = max(worst, best)
        if best > tolerance:
            return {'passed': False, 'max': best, 'worst_point': point.tolist(), 'samples': len(points)}
    return {'passed': True, 'max': worst, 'samples': len(points)}


def decimate_part(mesh, target, tolerance):
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray
    from vtkmodules.vtkFiltersCore import vtkQuadricDecimation
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
    if len(mesh.faces) <= target:
        return mesh.copy()
    points = vtkPoints()
    points.SetData(numpy_to_vtk(np.asarray(mesh.vertices, dtype=np.float64), deep=True))
    cells = vtkCellArray()
    packed = np.column_stack([np.full(len(mesh.faces), 3), mesh.faces]).astype(np.int64)
    cells.SetCells(len(mesh.faces), numpy_to_vtkIdTypeArray(packed.ravel(), deep=True))
    data = vtkPolyData()
    data.SetPoints(points)
    data.SetPolys(cells)
    algorithm = vtkQuadricDecimation()
    algorithm.SetInputData(data)
    algorithm.SetTargetReduction(1-target/len(mesh.faces))
    algorithm.VolumePreservationOn()
    algorithm.Update()
    output = algorithm.GetOutput()
    if not output.GetNumberOfPolys():
        raise ValueError('Thuật toán giảm lưới không tạo được mặt hợp lệ.')
    vertices = vtk_to_numpy(output.GetPoints().GetData()).copy()
    polygons = vtk_to_numpy(output.GetPolys().GetData()).reshape(-1, 4)
    if not np.all(polygons[:, 0] == 3):
        raise ValueError('Kết quả giảm lưới không phải lưới tam giác.')
    result = trimesh.Trimesh(vertices=vertices, faces=polygons[:, 1:].copy(), process=False)
    result.remove_unreferenced_vertices()
    return result


def simplify(mesh, target, tolerance, report):
    report.update({'requested': True, 'applied': False, 'accepted': False,
                   'algorithm': 'VTK QuadricDecimation; volume preservation; independently checked topology and sharp edges (30 degrees)',
                   'source_faces': len(mesh.faces), 'target_faces': int(target),
                   'tolerance': float(tolerance), 'max_volume_change': .01,
                   'limitations': 'Sampled checks; not a certified continuous error bound or complete self-intersection test.'})
    if len(mesh.faces) <= target:
        report.update(accepted=True, result_faces=len(mesh.faces), reason='Already within target; mesh unchanged')
        return mesh
    if tolerance > mesh.scale*.01:
        raise ValueError('Dung sai giảm lưới vượt 1% đường chéo chi tiết; hãy giảm dung sai.')
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError('Chỉ giảm lưới kín và có hướng mặt nhất quán. Hãy sửa lỗi lưới trước.')
    parts = list(mesh.split(only_watertight=False, repair=False))
    protected_faces = sum(len(p.faces) for p in parts if len(p.faces) <= 128)
    reducible_faces = len(mesh.faces)-protected_faces
    if protected_faces >= target:
        raise ValueError('Số mặt đích quá thấp để giữ nguyên các thành phần nhỏ; hãy tăng số mặt đích.')
    results, part_reports = [], []
    for part in parts:
        budget = len(part.faces) if len(part.faces) <= 128 else max(
            4, int(np.floor((target-protected_faces)*len(part.faces)/reducible_faces)))
        candidate = decimate_part(part, budget, tolerance)
        detail = {'source_faces': len(part.faces), 'result_faces': len(candidate.faces),
                  'source_euler': int(part.euler_number), 'result_euler': int(candidate.euler_number)}
        part_reports.append(detail)
        report['components'] = part_reports
        if (not candidate.is_watertight or not candidate.is_winding_consistent or
                not np.isfinite(candidate.vertices).all() or
                candidate.euler_number != part.euler_number or
                len(candidate.split(only_watertight=False, repair=False)) != 1):
            raise ValueError('Giảm lưới làm thay đổi độ kín, hướng mặt hoặc topology; đã từ chối kết quả.')
        volume_change = abs(abs(candidate.volume)-abs(part.volume))/max(abs(part.volume), 1e-30)
        detail['relative_volume_change'] = float(volume_change)
        if volume_change > .01 or np.max(np.abs(candidate.bounds-part.bounds)) > tolerance:
            raise ValueError('Giảm lưới làm thay đổi thể tích quá 1% hoặc kích thước bao quá dung sai.')
        source_sharp, result_sharp = sharp_segments(part), sharp_segments(candidate)
        detail['sharp_edges'] = {
            'source_to_result': feature_distance(source_sharp, result_sharp, tolerance),
            'result_to_source': feature_distance(result_sharp, source_sharp, tolerance)}
        if not all(v['passed'] for v in detail['sharp_edges'].values()):
            raise ValueError('Giảm lưới không giữ được các cạnh sắc được kiểm tra trong dung sai.')
        detail['surface_deviation'] = compare_meshes(part, candidate, tolerance)
        if not detail['surface_deviation']['passed']:
            raise ValueError('Sai lệch bề mặt sau giảm lưới vượt dung sai; hãy tăng số mặt đích.')
        results.append(candidate)
    reduced = trimesh.util.concatenate(results)
    report['result_faces'] = len(reduced.faces)
    if len(reduced.faces) > target:
        raise ValueError(f'Chỉ giảm được tới {len(reduced.faces)} mặt khi giữ topology/cạnh sắc; chưa đạt mục tiêu {target}.')
    report.update(applied=True, accepted=True, reason='Topology, sampled sharp-edge/surface and volume checks passed')
    return reduced
