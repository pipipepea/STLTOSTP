import React from "react";
import { Check, AlertTriangle } from "lucide-react";

const names = {
  plane: "Phẳng",
  cylinder: "Trụ",
  cone: "Nón",
  sphere: "Cầu",
  torus: "Xuyến",
  revolution: "Tròn xoay",
  extrusion: "Khối đùn / lỗ tròn",
  surfaceofrevolution: "Mặt tròn xoay",
  bsplinesurface: "B-spline",
};
function types(value) {
  return Object.entries(value || {})
    .map(([k, n]) => `${n} ${names[k] || k}`)
    .join(" · ");
}
function reason(text = "") {
  if (text.includes("1%"))
    return "Dung sai vượt 1% đường chéo chi tiết. Hãy giảm dung sai.";
  if (text.includes("Volume change")) return "Thay đổi thể tích vượt giới hạn.";
  if (text.includes("Mesh-to-CAD"))
    return "Sai lệch từ lưới tới CAD vượt dung sai.";
  if (text.includes("CAD-to-mesh"))
    return "Sai lệch từ CAD về lưới vượt dung sai.";
  if (text.includes("topology"))
    return "Phục dựng có thể làm thay đổi topology.";
  if (text.includes("Bounding-box"))
    return "Kích thước bao thay đổi quá dung sai.";
  return "Chưa tìm được dạng bề mặt hỗ trợ đạt tất cả kiểm tra.";
}
const number = (value) =>
  Number.isFinite(value)
    ? value.toLocaleString("vi-VN", { maximumSignificantDigits: 4 })
    : "—";

export default function CurveReport({ reconstruction, surfaceTypes, unit }) {
  if (!reconstruction || reconstruction.mode === "off") return null;
  const components = reconstruction.components || [];
  const accepted = components.filter((c) => c.accepted).length;
  return (
    <section
      className="curve-report"
      aria-label="Kết quả phục dựng bề mặt cong"
    >
      <div className="curve-report-heading">
        <div>
          <h3>Bề mặt CAD chuẩn</h3>
          <p>
            {accepted}/{components.length} thành phần được phục dựng · Dung sai{" "}
            {number(reconstruction.fit_tolerance)} {unit}
          </p>
        </div>
        <span className="surface-badge">
          {types(surfaceTypes) || "Chưa có STEP hợp lệ"}
        </span>
      </div>
      <div className="curve-table-scroll">
        <table>
          <thead>
            <tr>
              <th>Thành phần</th>
              <th>Kết quả</th>
              <th>Loại bề mặt</th>
              <th>Sai lệch lấy mẫu</th>
              <th>Δ thể tích</th>
            </tr>
          </thead>
          <tbody>
            {components.map((c, i) => (
              <tr key={c.component ?? i}>
                <td>
                  #{(c.component ?? i) + 1}
                  <small>
                    {c.source_faces?.toLocaleString("vi-VN")} tam giác đầu vào
                    CAD
                  </small>
                </td>
                <td>
                  <span
                    className={c.accepted ? "fit-accepted" : "fit-fallback"}
                  >
                    {c.accepted ? (
                      <Check size={13} />
                    ) : (
                      <AlertTriangle size={13} />
                    )}{" "}
                    {c.accepted
                      ? "Đã phục dựng"
                      : reconstruction.mode === "required"
                        ? "Không đạt"
                        : "Giữ mặt gốc"}
                  </span>
                </td>
                <td>
                  {c.accepted
                    ? types(c.surface_types)
                    : "Chưa khớp đạt yêu cầu"}
                </td>
                <td>
                  {c.accepted ? (
                    <>
                      {number(Math.max(c.mesh_to_cad.max, c.cad_to_mesh.max))}{" "}
                      {unit}
                      <small>
                        STL → CAD: {number(c.mesh_to_cad.max)}
                        <br />
                        CAD → STL: {number(c.cad_to_mesh.max)}
                      </small>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  {c.accepted
                    ? `${number(c.relative_volume_change * 100)}%`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {components.some((c) => !c.accepted) && (
        <details className="fit-reasons">
          <summary>Vì sao có thành phần chưa phục dựng?</summary>
          {components
            .filter((c) => !c.accepted)
            .map((c, i) => (
              <div key={i}>
                <strong>Thành phần #{c.component + 1}:</strong>{" "}
                {reason(c.reason)}
                {c.attempts?.length > 0 && (
                  <ul>
                    {c.attempts.slice(0, 6).map((a, j) => (
                      <li key={j}>
                        {names[a.parameters?.type] || "Ứng viên"}:{" "}
                        {reason(a.reason)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
        </details>
      )}
      <p className="measurement-note">
        Đo hai chiều bằng các điểm trên bề mặt, đỉnh, tâm tam giác và trung điểm
        cạnh. Giá trị lớn nhất được lấy mẫu; chưa phải bảo đảm sai lệch liên tục
        trên toàn bề mặt. Xem tham số khớp và vị trí sai lệch lớn nhất trong báo
        cáo JSON.
      </p>
    </section>
  );
}
