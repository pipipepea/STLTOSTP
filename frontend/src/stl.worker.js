import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
self.onmessage = ({ data }) => {
  try {
    const geometry = new STLLoader().parse(data);
    if (!geometry.attributes.position?.count)
      throw new Error("Không tìm thấy tam giác trong STL.");
    const positions = geometry.attributes.position.array;
    if (!positions.every(Number.isFinite))
      throw new Error("STL chứa tọa độ không hợp lệ.");
    geometry.computeVertexNormals();
    const normals = geometry.attributes.normal.array;
    self.postMessage({ positions, normals }, [
      positions.buffer,
      normals.buffer,
    ]);
    geometry.dispose();
  } catch (error) {
    self.postMessage({ error: error.message });
  }
};
