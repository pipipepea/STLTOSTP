import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export default function Viewer({
  data,
  wireframe = false,
  issues = [],
  label,
  empty,
}) {
  const host = useRef(null);
  useEffect(() => {
    if (!data || !host.current) return;
    const container = host.current;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      container.textContent = "Trình duyệt không hỗ trợ WebGL.";
      return () => {
        container.textContent = "";
      };
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 10000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(data.positions, 3),
    );
    geometry.setAttribute("normal", new THREE.BufferAttribute(data.normals, 3));
    geometry.computeBoundingBox();
    const center = geometry.boundingBox.getCenter(new THREE.Vector3());
    const size = geometry.boundingBox.getSize(new THREE.Vector3());
    const extent = Math.max(size.x, size.y, size.z, 1e-9);
    const model = new THREE.Group();
    // Normalize display only. Original coordinates and file units are preserved.
    model.scale.setScalar(3 / extent);
    model.position.copy(center).multiplyScalar(-3 / extent);
    const material = new THREE.MeshStandardMaterial({
      color: wireframe ? 0x92a5ae : 0x32a69a,
      metalness: 0.2,
      roughness: 0.5,
      side: THREE.DoubleSide,
      wireframe,
    });
    model.add(new THREE.Mesh(geometry, material));
    const helpers = [];
    for (const issue of issues) {
      if (!issue.bounds) continue;
      const helper = new THREE.Box3Helper(
        new THREE.Box3(
          new THREE.Vector3(...issue.bounds.min),
          new THREE.Vector3(...issue.bounds.max),
        ),
        0xef824d,
      );
      model.add(helper);
      helpers.push(helper);
    }
    scene.add(model);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x7e929b, 2.5));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(3, 5, 4);
    scene.add(light);
    const grid = new THREE.GridHelper(12, 24, 0xc8d4d8, 0xe0e7e9);
    grid.position.y = -1.9;
    scene.add(grid);
    camera.position.set(5, 4.1, 5);
    camera.lookAt(0, 0, 0);
    const resize = () => {
      const w = container.clientWidth,
        h = container.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();
    let frame;
    function animate() {
      frame = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      geometry.dispose();
      material.dispose();
      helpers.forEach((h) => {
        h.geometry.dispose();
        h.material.dispose();
      });
      grid.geometry.dispose();
      grid.material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [data, wireframe, issues]);
  return (
    <div className="viewport">
      <div className="view-label">
        <span className={wireframe ? "dot muted" : "dot"} />
        {label}
      </div>
      <div className="three-host" ref={host} />
      {!data && <div className="view-empty">{empty}</div>}
      <div className="axis">
        <b>Z</b>
        <span>Y</span>
        <i>X</i>
      </div>
      <span className="view-help">Kéo để xoay · Cuộn để thu phóng</span>
    </div>
  );
}
