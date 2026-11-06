import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Box,
  Upload,
  ArrowUpRight,
  ArrowRight,
  Download,
  Layers3,
  Check,
  FileBox,
  ShieldCheck,
  Activity,
  SlidersHorizontal,
  KeyRound,
  X,
  AlertTriangle,
  RotateCcw,
  LoaderCircle,
} from "lucide-react";
import Viewer from "./Viewer";
import CurveReport from "./CurveReport";
import SimplificationReport from "./SimplificationReport";
import "./style.css";

const EMPTY = [];
const issueNames = {
  boundary_edges: "Cạnh hở",
  non_manifold_edges: "Cạnh phi đa tạp",
  duplicate_faces: "Mặt trùng",
  degenerate_faces: "Mặt suy biến",
};
const repairNames = {
  remove_degenerate_faces: "Loại mặt suy biến",
  remove_duplicate_faces: "Loại mặt trùng",
  orient_faces: "Sửa hướng mặt",
};
function parseSTL(buffer) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./stl.worker.js", import.meta.url), {
      type: "module",
    });
    worker.onmessage = ({ data }) => {
      worker.terminate();
      data.error ? reject(new Error(data.error)) : resolve(data);
    };
    worker.onerror = () => {
      worker.terminate();
      reject(new Error("Không đọc được STL."));
    };
    worker.postMessage(buffer, [buffer]);
  });
}
function demoFile() {
  const v = [
    [-10, -10, 0],
    [10, -10, 0],
    [10, 10, 0],
    [-10, 10, 0],
    [-10, -10, 12],
    [10, -10, 12],
    [10, 10, 12],
    [-10, 10, 12],
  ];
  const f = [
    [0, 2, 1],
    [0, 3, 2],
    [4, 5, 6],
    [4, 6, 7],
    [0, 1, 5],
    [0, 5, 4],
    [1, 2, 6],
    [1, 6, 5],
    [2, 3, 7],
    [2, 7, 6],
    [3, 0, 4],
    [3, 4, 7],
  ];
  return new File(
    [
      "solid sample\n" +
        f
          .map(
            (t) =>
              "facet normal 0 0 0\nouter loop\n" +
              t.map((i) => "vertex " + v[i].join(" ")).join("\n") +
              "\nendloop\nendfacet",
          )
          .join("\n") +
        "\nendsolid sample",
    ],
    "sample-block.stl",
    { type: "model/stl" },
  );
}
function cylinderDemoFile() {
  const vertices = [
      [0, 0, 0],
      [0, 0, 12],
    ],
    faces = [];
  const count = 64;
  for (let i = 0; i < count; i++) {
    const a = (i * 2 * Math.PI) / count;
    vertices.push(
      [5 * Math.cos(a), 5 * Math.sin(a), 0],
      [5 * Math.cos(a), 5 * Math.sin(a), 12],
    );
  }
  for (let i = 0; i < count; i++) {
    const bottom = 2 + i * 2,
      top = bottom + 1;
    const nextBottom = 2 + ((i + 1) % count) * 2,
      nextTop = nextBottom + 1;
    faces.push(
      [0, nextBottom, bottom],
      [1, top, nextTop],
      [bottom, nextBottom, nextTop],
      [bottom, nextTop, top],
    );
  }
  const stl =
    "solid cylinder\n" +
    faces
      .map(
        (f) =>
          "facet normal 0 0 0\nouter loop\n" +
          f.map((i) => "vertex " + vertices[i].join(" ")).join("\n") +
          "\nendloop\nendfacet",
      )
      .join("\n") +
    "\nendsolid cylinder";
  return new File([stl], "sample-cylinder-r5-h12.stl", { type: "model/stl" });
}
function App() {
  const [file, setFile] = useState(null),
    [source, setSource] = useState(null),
    [result, setResult] = useState(null),
    [report, setReport] = useState(null);
  const [unit, setUnit] = useState("mm"),
    [merge, setMerge] = useState(true),
    [wire, setWire] = useState(false),
    [showIssues, setShowIssues] = useState(true);
  const [curveMode, setCurveMode] = useState("auto");
  const [fitTolerance, setFitTolerance] = useState("0.05");
  const [volumeLimit, setVolumeLimit] = useState("2");
  const [simplifyMesh, setSimplifyMesh] = useState(false);
  const [targetFaces, setTargetFaces] = useState("25000");
  const [simplifyTolerance, setSimplifyTolerance] = useState("0.05");
  const [limits, setLimits] = useState({
    max_input_faces: 200000,
    max_cad_faces: 30000,
    max_upload_bytes: 30 * 1024 * 1024,
  });
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/config", { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((value) => {
        if (
          value &&
          ["max_input_faces", "max_cad_faces", "max_upload_bytes"].every(
            (k) => Number.isFinite(value[k]) && value[k] > 0,
          )
        ) {
          setLimits(value);
          setTargetFaces((previous) =>
            previous === "25000"
              ? String(
                  value.default_target_faces ||
                    Math.min(25000, value.max_cad_faces),
                )
              : previous,
          );
        }
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  const [busy, setBusy] = useState(false),
    [reading, setReading] = useState(false),
    [job, setJob] = useState(null),
    [status, setStatus] = useState(null),
    [error, setError] = useState("");
  const [key, setKey] = useState(""),
    [keyOpen, setKeyOpen] = useState(false),
    [drag, setDrag] = useState(false);
  const input = useRef(null),
    selection = useRef(0),
    keyInput = useRef(null);
  useEffect(() => {
    if (keyOpen) keyInput.current?.focus();
  }, [keyOpen]);
  async function choose(f) {
    if (!f) return;
    const current = ++selection.current;
    setError("");
    if (!f.name.toLowerCase().endsWith(".stl")) {
      setError("Vui lòng chọn file STL.");
      return;
    }
    if (f.size > limits.max_upload_bytes) {
      setError(
        `Giới hạn tải lên là ${Math.floor(limits.max_upload_bytes / 1024 / 1024)} MB.`,
      );
      return;
    }
    setReading(true);
    setJob(null);
    setStatus(null);
    setReport(null);
    setResult(null);
    setSource(null);
    setFile(f);
    try {
      const data = await parseSTL(await f.arrayBuffer());
      if (data.positions.length / 9 > limits.max_input_faces)
        throw new Error(
          `Lưới vượt giới hạn đọc ${limits.max_input_faces.toLocaleString("vi-VN")} mặt.`,
        );
      if (current === selection.current) setSource(data);
    } catch (e) {
      if (current === selection.current) {
        setError(e.message);
        setFile(null);
      }
    } finally {
      if (current === selection.current) setReading(false);
    }
  }
  async function start() {
    if (
      simplifyMesh &&
      (!Number.isInteger(Number(targetFaces)) ||
        Number(targetFaces) < 4 ||
        Number(targetFaces) > limits.max_cad_faces ||
        !Number.isFinite(Number(simplifyTolerance)) ||
        Number(simplifyTolerance) <= 0)
    ) {
      setError(
        `Số mặt đích phải là số nguyên từ 4 đến ${limits.max_cad_faces}; dung sai giảm lưới phải lớn hơn 0.`,
      );
      return;
    }
    if (
      curveMode !== "off" &&
      (!Number.isFinite(Number(fitTolerance)) ||
        Number(fitTolerance) <= 0 ||
        !Number.isFinite(Number(volumeLimit)) ||
        Number(volumeLimit) <= 0 ||
        Number(volumeLimit) > 5)
    ) {
      setError(
        "Dung sai phải lớn hơn 0; giới hạn thay đổi thể tích từ lớn hơn 0 đến 5%.",
      );
      return;
    }
    if (!key) {
      setKeyOpen(true);
      return;
    }
    setBusy(true);
    setError("");
    setReport(null);
    setResult(null);
    setStatus({
      state: "uploading",
      progress: 0,
      message: "Đang tải STL lên máy chủ",
    });
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("unit", unit);
      form.append("merge_planes", String(merge));
      form.append("curve_mode", curveMode);
      form.append("simplify_mesh", String(simplifyMesh));
      if (simplifyMesh) {
        form.append("target_faces", targetFaces);
        form.append("simplify_tolerance", simplifyTolerance);
      }
      form.append("fit_tolerance", curveMode === "off" ? "0.05" : fitTolerance);
      form.append(
        "max_volume_change",
        curveMode === "off" ? "0.02" : String(Number(volumeLimit) / 100),
      );
      const r = await fetch("/api/jobs", {
        method: "POST",
        headers: { "X-API-Key": key },
        body: form,
      });
      const value = await r.json();
      if (!r.ok)
        throw new Error(
          typeof value.detail === "string"
            ? value.detail
            : "Không gửi được tác vụ.",
        );
      setJob(value);
    } catch (e) {
      setError(e.message);
      setBusy(false);
      setStatus(null);
    }
  }
  useEffect(() => {
    if (!job) return;
    let active = true,
      finished = false,
      loading = false;
    const headers = { "X-Job-Token": job.token };
    const url = `/api/jobs/${job.task_id}`;
    async function accept(s) {
      if (!active || finished) return;
      setStatus(s);
      if (s.state === "completed" || s.state === "failed") {
        finished = true;
        setBusy(false);
        if (s.state === "failed") setError(s.message);
        try {
          const response = await fetch(url + "/files/report", { headers });
          if (response.ok && active) setReport(await response.json());
          if (s.state === "completed") {
            const preview = await fetch(url + "/files/preview", { headers });
            if (!preview.ok)
              throw new Error("Không tải được bản xem trước STEP.");
            const data = await parseSTL(await preview.arrayBuffer());
            if (active) setResult(data);
          }
        } catch (e) {
          if (active) setError(e.message);
        }
      }
    }
    async function poll() {
      if (loading || finished) return;
      loading = true;
      try {
        const r = await fetch(url, { headers });
        if (!r.ok)
          throw new Error("Không đọc được tác vụ hoặc tác vụ đã hết hạn.");
        await accept(await r.json());
      } catch (e) {
        if (active) {
          setError(e.message);
          setBusy(false);
          finished = true;
        }
      } finally {
        loading = false;
      }
    }
    const socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${url}/events`,
    );
    socket.onopen = () => socket.send(JSON.stringify({ token: job.token }));
    socket.onmessage = ({ data }) => {
      try {
        accept(JSON.parse(data));
      } catch {
        /* polling recovers */
      }
    };
    socket.onerror = () => {};
    poll();
    const timer = setInterval(poll, 2500);
    return () => {
      active = false;
      clearInterval(timer);
      socket.close();
    };
  }, [job]);
  async function download(kind) {
    try {
      const r = await fetch(`/api/jobs/${job.task_id}/files/${kind}`, {
        headers: { "X-Job-Token": job.token },
      });
      if (!r.ok) throw new Error("File chưa sẵn sàng hoặc đã hết hạn.");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download =
        kind === "step"
          ? "result.step"
          : kind === "report"
            ? "report.json"
            : kind === "simplified"
              ? "simplified.stl"
              : "repaired.stl";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e.message);
    }
  }
  const complete = status?.state === "completed";
  const issues = report?.after?.issues || EMPTY;
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="STL to STP trang chủ">
          <div className="brand-icon">
            <Box size={24} />
          </div>
          <span>
            FORM<span className="brand-light">SHIFT</span>
            <small>STL TO STEP WORKBENCH</small>
          </span>
        </a>
        <div className="workspace-label">KHÔNG GIAN LÀM VIỆC</div>
        <div className="nav-item active">
          <Layers3 size={18} /> Chuyển đổi CAD <span>01</span>
        </div>
        <div className="side-note">
          <div className="mini-grid">
            <Box size={40} />
          </div>
          <h3>Từ lưới đến solid.</h3>
          <p>
            Kiểm tra hình học.
            <br />
            Giữ nguyên chi tiết.
            <br />
            Sẵn sàng cho CAD.
          </p>
          <div className="engine-pill">
            <span className="dot" /> OCCT ENGINE
          </div>
        </div>
        <div className="sidebar-bottom">
          <ShieldCheck size={17} />
          <span>
            File tự hết hạn sau 24 giờ
            <small>Mặc định khi chạy bằng Docker</small>
          </span>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            Workspace <span>/</span> Chuyển đổi CAD
          </div>
          <button className="key-button" onClick={() => setKeyOpen(true)}>
            <KeyRound size={15} />
            {key ? "Đã nhập API key" : "Kết nối máy chủ"}
            <span className={key ? "dot" : "dot muted"} />
          </button>
        </header>
        <div className="page">
          <div className="heading">
            <div>
              <div className="eyebrow">MESH IN. SOLID OUT.</div>
              <h1>
                Chuyển đổi STL sang STEP<span>.</span>
              </h1>
              <p>
                Kiểm tra, sửa lưới và dựng solid CAD — với kết quả được xác
                minh.
              </p>
            </div>
            <div className="version">
              MESH & SURFACES <b>v0.3</b>
            </div>
          </div>
          <div className="workflow">
            <span className="workflow-step">
              <b>01</b> Tải mô hình
            </span>
            <ArrowRight size={16} />
            <span className={busy ? "workflow-step current" : "workflow-step"}>
              <b>02</b> Phân tích & dựng khối
            </span>
            <ArrowRight size={16} />
            <span
              className={complete ? "workflow-step current" : "workflow-step"}
            >
              <b>03</b> Xác minh & xuất STEP
            </span>
            <span className="cpu-label">CPU · Không cần GPU</span>
          </div>
          <div className="workbench">
            <section className="settings">
              <div className="panel-heading">
                <h2>
                  <FileBox size={17} /> Mô hình đầu vào
                </h2>
                <span>01</span>
              </div>
              <button
                disabled={busy || reading}
                className={"dropzone " + (drag ? "drag" : "")}
                onClick={() => input.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDrag(false);
                  if (!busy && !reading) choose(e.dataTransfer.files[0]);
                }}
              >
                <span className="upload-icon">
                  {reading ? (
                    <LoaderCircle className="spin" size={24} />
                  ) : (
                    <Upload size={24} />
                  )}
                </span>
                <strong>{file ? file.name : "Kéo thả file STL vào đây"}</strong>
                <span>
                  {file
                    ? (file.size / 1024).toFixed(1) + " KB · Nhấn để đổi file"
                    : "hoặc nhấn để chọn từ thiết bị"}
                </span>
                <small>
                  .STL · {Math.floor(limits.max_upload_bytes / 1024 / 1024)} MB
                  / {limits.max_input_faces.toLocaleString("vi-VN")} mặt nguồn
                </small>
              </button>
              <div className="sample-actions">
                <button
                  className="sample curved-sample"
                  disabled={busy || reading}
                  onClick={() => choose(cylinderDemoFile())}
                >
                  Thử trụ R5 × H12 <ArrowUpRight size={14} />
                </button>
                <input
                  ref={input}
                  type="file"
                  accept=".stl"
                  hidden
                  onChange={(e) => choose(e.target.files[0])}
                />
                <button
                  className="sample"
                  disabled={busy || reading}
                  onClick={() => choose(demoFile())}
                >
                  Chưa có file? Thử khối mẫu <ArrowUpRight size={14} />
                </button>
              </div>
              <div className="section-title">
                <SlidersHorizontal size={16} /> Thiết lập chuyển đổi
              </div>
              <label className="field-label" htmlFor="unit">
                Đơn vị của file STL
              </label>
              <select
                id="unit"
                value={unit}
                disabled={busy}
                onChange={(e) => setUnit(e.target.value)}
              >
                <option value="mm">Millimeter (mm)</option>
                <option value="cm">Centimeter (cm)</option>
                <option value="m">Meter (m)</option>
                <option value="inch">Inch (in)</option>
              </select>
              <p className="field-hint">
                STL không lưu đơn vị. Chọn đúng đơn vị nguồn; tọa độ không bị
                đổi tỷ lệ.
              </p>
              <label className="toggle-row">
                <span>
                  <strong>Gộp mặt đồng phẳng</strong>
                  <small>Loại đường chia tam giác trên mặt phẳng</small>
                </span>
                <input
                  type="checkbox"
                  checked={merge}
                  disabled={busy}
                  onChange={(e) => setMerge(e.target.checked)}
                />
              </label>
              <div className="info-box">
                <ShieldCheck size={18} />
                <p>
                  Chỉ xuất STEP sau khi kiểm tra solid và đọc lại file thành
                  công.
                </p>
              </div>
              <fieldset className="advanced-settings" disabled={busy}>
                <legend>Bề mặt cong · nâng cao</legend>
                <label htmlFor="curve-mode">Chế độ phục dựng</label>
                <select
                  id="curve-mode"
                  value={curveMode}
                  onChange={(e) => setCurveMode(e.target.value)}
                >
                  <option value="auto">
                    Tự động · giữ mặt gốc nếu không đạt
                  </option>
                  <option value="required">Bắt buộc khớp mọi thành phần</option>
                  <option value="off">Tắt · chỉ gộp mặt phẳng</option>
                </select>
                {curveMode !== "off" && (
                  <>
                    <div className="fit-controls">
                      <label htmlFor="fit-tolerance">
                        Dung sai ({unit})
                        <input
                          id="fit-tolerance"
                          type="number"
                          min="0.0000001"
                          step="any"
                          value={fitTolerance}
                          onChange={(e) => setFitTolerance(e.target.value)}
                        />
                      </label>
                      <label htmlFor="volume-limit">
                        Δ thể tích tối đa (%)
                        <input
                          id="volume-limit"
                          type="number"
                          min="0.000001"
                          max="5"
                          step="any"
                          value={volumeLimit}
                          onChange={(e) => setVolumeLimit(e.target.value)}
                        />
                      </label>
                    </div>
                    <p>
                      Trụ, nón, cầu, xuyến, chi tiết tròn xoay và khối đùn có lỗ
                      tròn/cung bo. Chưa phục dựng NURBS tự do.
                    </p>
                    {curveMode === "required" && (
                      <p className="strict-note">
                        Không xuất STEP nếu có thành phần không khớp được, kể cả
                        khối hộp.
                      </p>
                    )}
                  </>
                )}
              </fieldset>
              <fieldset
                className="advanced-settings simplification-settings"
                disabled={busy}
              >
                <legend>Giảm lưới · tùy chọn</legend>
                <label className="simplify-toggle">
                  <input
                    type="checkbox"
                    checked={simplifyMesh}
                    onChange={(e) => setSimplifyMesh(e.target.checked)}
                  />{" "}
                  Giảm lưới trước chuyển đổi
                </label>
                {source &&
                  source.positions.length / 9 > limits.max_cad_faces &&
                  !simplifyMesh && (
                    <p className="strict-note">
                      Lưới có{" "}
                      {(source.positions.length / 9).toLocaleString("vi-VN")}{" "}
                      mặt, vượt giới hạn CAD{" "}
                      {limits.max_cad_faces.toLocaleString("vi-VN")}. Bật giảm
                      lưới để tiếp tục.
                    </p>
                  )}
                {simplifyMesh && (
                  <>
                    <div className="fit-controls">
                      <label htmlFor="target-faces">
                        Số mặt đích
                        <input
                          id="target-faces"
                          type="number"
                          min="4"
                          max={limits.max_cad_faces}
                          step="1"
                          value={targetFaces}
                          onChange={(e) => setTargetFaces(e.target.value)}
                        />
                      </label>
                      <label htmlFor="simplify-tolerance">
                        Dung sai ({unit})
                        <input
                          id="simplify-tolerance"
                          type="number"
                          min="0.0000001"
                          step="any"
                          value={simplifyTolerance}
                          onChange={(e) => setSimplifyTolerance(e.target.value)}
                        />
                      </label>
                    </div>
                    <p>
                      Giữ file gốc. Chỉ nhận kết quả đạt kiểm tra độ kín,
                      topology, cạnh sắc và sai lệch lấy mẫu; thể tích thay đổi
                      tối đa 1%. Giảm lưới có thể làm mất chi tiết dưới dung
                      sai.
                    </p>
                  </>
                )}
              </fieldset>
              <button
                className="primary"
                disabled={!file || !source || busy || reading}
                onClick={start}
              >
                {busy ? (
                  <>
                    <LoaderCircle size={17} className="spin" /> Đang xử lý
                  </>
                ) : (
                  <>
                    <span>
                      {complete ? "Chuyển đổi lại" : "Chuyển sang STEP"}
                    </span>
                    <ArrowRight size={17} />
                  </>
                )}
              </button>
            </section>
            <section className="preview-panel">
              <div className="panel-heading">
                <h2>
                  <Box size={18} /> Không gian 3D
                </h2>
                <div className="preview-actions">
                  <button
                    className={wire ? "selected" : ""}
                    onClick={() => setWire(!wire)}
                    aria-pressed={wire}
                  >
                    Lưới
                  </button>
                  <button
                    className={showIssues ? "selected" : ""}
                    onClick={() => setShowIssues(!showIssues)}
                    aria-pressed={showIssues}
                  >
                    Vùng lỗi
                  </button>
                </div>
              </div>
              <div className="viewers">
                <Viewer
                  label="STL GỐC"
                  data={source}
                  wireframe={wire}
                  issues={showIssues ? issues : EMPTY}
                  empty={
                    <>
                      <Box size={46} strokeWidth={1} />
                      <strong>Mô hình của bạn bắt đầu ở đây</strong>
                      <span>Tải STL hoặc mở khối mẫu để xem 3D</span>
                    </>
                  }
                />
                <Viewer
                  label="STEP SAU XÁC MINH"
                  data={result}
                  empty={
                    <>
                      <Layers3 size={46} strokeWidth={1} />
                      <strong>
                        {busy
                          ? "Đang dựng mô hình CAD"
                          : "Chờ kết quả chuyển đổi"}
                      </strong>
                      <span>Bản xem được tạo từ STEP đã nhập lại</span>
                    </>
                  }
                />
              </div>
              <div className="preview-footer">
                <span>
                  <span className="dot" />
                  {source
                    ? (source.positions.length / 9).toLocaleString("vi-VN") +
                      " tam giác"
                    : "Chưa có mô hình"}
                </span>
                <span>Orbit controls · WebGL</span>
              </div>
            </section>
          </div>
          {error && (
            <div className="error" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="Đóng thông báo" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          <section className="results">
            <div className="panel-heading">
              <h2>
                <Activity size={17} /> Phân tích & kết quả
              </h2>
              <span className={"status-tag " + (complete ? "done" : "")}>
                {status
                  ? {
                      queued: "Đang chờ",
                      uploading: "Đang tải lên",
                      running: "Đang xử lý",
                      completed: "Hoàn thành",
                      failed: "Cần kiểm tra",
                    }[status.state]
                  : "Sẵn sàng"}
              </span>
            </div>
            {status && (
              <div className="progress-block">
                <div>
                  <span>{status.message}</span>
                  <b>{status.progress}%</b>
                </div>
                <div className="progress-track">
                  <div style={{ width: status.progress + "%" }} />
                </div>
              </div>
            )}
            {report ? (
              <>
                <div className="metrics">
                  <Metric
                    label="MẶT TAM GIÁC GỐC"
                    value={report.before?.faces?.toLocaleString("vi-VN") ?? "—"}
                  />
                  <Metric
                    label="MẶT B-REP SAU XUẤT"
                    value={report.verification?.after_reimport?.faces ?? "—"}
                  />
                  <Metric
                    label="SOLID HỢP LỆ"
                    value={report.verification?.after_reimport?.solids ?? "—"}
                    success={complete}
                  />
                  <Metric label="ĐƠN VỊ NGUỒN" value={report.unit} />
                </div>
                <CurveReport
                  reconstruction={report.curve_reconstruction}
                  surfaceTypes={report.surface_types}
                  unit={report.unit}
                />
                <SimplificationReport
                  info={report.simplification}
                  verification={report.verification}
                  unit={report.unit}
                />
                <div className="report-details">
                  <div>
                    <h3>Lưới trước và sau sửa</h3>
                    {report.before?.issues?.length ? (
                      <ul>
                        {report.before.issues.map((i) => (
                          <li key={i.type}>
                            {issueNames[i.type] || i.type}: <b>{i.count}</b>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>
                        Không phát hiện lỗi cạnh hở, phi đa tạp, mặt trùng hoặc
                        suy biến.
                      </p>
                    )}
                    {report.repairs?.map((r, i) => (
                      <p key={i}>
                        <Check size={14} /> {repairNames[r.action] || r.action}:{" "}
                        {r.count}
                      </p>
                    ))}
                    <p>
                      Còn lại sau sửa: {issues.reduce((n, i) => n + i.count, 0)}{" "}
                      phần tử lỗi.
                    </p>
                  </div>
                  <div>
                    <h3>Phạm vi xác minh</h3>
                    <p>
                      {complete
                        ? "Đã kiểm tra B-rep, thể tích, kích thước bao và nhập lại STEP."
                        : "Chưa xuất STEP. Xem báo cáo để xác định vùng cần sửa."}
                    </p>
                    <p>
                      {report.curve_reconstruction?.accepted_components > 0
                        ? "Bề mặt cong đã qua kiểm tra sai lệch hai chiều và giới hạn thể tích. Những thành phần không đạt vẫn giữ mặt gốc trong chế độ tự động."
                        : "Chưa có thành phần cong được phục dựng đạt yêu cầu; các vùng cong vẫn có thể gồm nhiều mặt tam giác."}{" "}
                      Chưa kiểm tra đầy đủ tự giao của mesh.
                    </p>
                  </div>
                </div>
                <div className="downloads">
                  {complete && (
                    <button
                      className="primary"
                      onClick={() => download("step")}
                    >
                      <Download size={17} /> Tải STEP
                    </button>
                  )}
                  <button
                    className="secondary"
                    onClick={() => download("report")}
                  >
                    <Download size={16} /> Báo cáo JSON
                  </button>
                  {report.after && (
                    <button
                      className="secondary"
                      onClick={() => download("repaired")}
                    >
                      <Download size={16} /> STL đã sửa
                    </button>
                  )}
                  {report.simplification?.applied &&
                    report.simplification?.accepted && (
                      <button
                        className="secondary"
                        onClick={() => download("simplified")}
                      >
                        <Download size={16} /> STL đã giảm lưới
                      </button>
                    )}
                </div>
              </>
            ) : (
              <div className="results-empty">
                <div className="check-icon">
                  <ShieldCheck size={24} />
                </div>
                <div>
                  <h3>
                    {busy
                      ? "Mô hình đang được xử lý trên máy chủ"
                      : "Mỗi lần chuyển đổi, một báo cáo rõ ràng."}
                  </h3>
                  <p>
                    Lỗi hình học, các bước sửa và kết quả kiểm tra được ghi lại
                    theo từng tác vụ.
                  </p>
                </div>
                <span>Kiểm tra → Sửa → Xác minh</span>
              </div>
            )}
          </section>
          <footer>
            <span>
              FORM<span>SHIFT</span> <i>/</i> STL to STEP
            </span>
            <span>Giữ hình dạng. Hiểu giới hạn. Kiểm chứng kết quả.</span>
            <a
              href="https://github.com/pipipepea/STLTOSTP"
              target="_blank"
              rel="noreferrer"
            >
              Mã nguồn <ArrowUpRight size={13} />
            </a>
          </footer>
        </div>
      </main>
      {keyOpen && (
        <div className="modal-backdrop" onClick={() => setKeyOpen(false)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="key-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setKeyOpen(false);
            }}
          >
            <button
              className="modal-close"
              aria-label="Đóng"
              onClick={() => setKeyOpen(false)}
            >
              <X size={20} />
            </button>
            <KeyRound size={26} />
            <h2 id="key-title">Kết nối máy chủ</h2>
            <p>
              Nhập API key đã cấu hình trên VPS. Khóa chỉ được giữ trong bộ nhớ
              của trang hiện tại.
            </p>
            <label htmlFor="api-key">API key</label>
            <input
              ref={keyInput}
              id="api-key"
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              autoComplete="off"
              placeholder="Nhập API key của bạn"
            />
            <button className="primary" onClick={() => setKeyOpen(false)}>
              Lưu cho phiên này <Check size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
function Metric({ label, value, success }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={success ? "teal" : ""}>
        {value}
        {success && <Check size={18} />}
      </strong>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
