import React from "react";

const number = (value) =>
  Number.isFinite(value)
    ? value.toLocaleString("vi-VN", { maximumSignificantDigits: 5 })
    : "—";
export default function SimplificationReport({ info, verification, unit }) {
  if (!info?.requested) return null;
  const parts = info.components || [];
  const max = (field) =>
    Math.max(0, ...parts.map((p) => p.surface_deviation?.[field]?.max || 0));
  return (
    <section className="simplification-report" aria-label="Kết quả giảm lưới">
      <h3>Giảm lưới trước chuyển đổi</h3>
      <p>
        <strong>{number(info.source_faces)}</strong> →{" "}
        <strong>{number(info.result_faces)}</strong> tam giác · Mục tiêu{" "}
        {number(info.target_faces)}
      </p>
      {info.applied && info.accepted ? (
        <>
          <p>
            Đã kiểm tra độ kín, số thành phần, Euler, cạnh sắc lấy mẫu và thay
            đổi thể tích từng thành phần không quá 1%.
          </p>
          <p>
            Sai lệch lấy mẫu: gốc → giảm{" "}
            <b>
              {number(max("source_to_result"))} {unit}
            </b>
            ; giảm → gốc{" "}
            <b>
              {number(max("result_to_source"))} {unit}
            </b>
            . Dung sai: {number(info.tolerance)} {unit}.
          </p>
        </>
      ) : (
        <p>
          {info.rejection_reason ||
            (info.accepted
              ? "Số mặt đã nằm trong mục tiêu; không thay đổi lưới."
              : "Chưa chấp nhận kết quả giảm lưới.")}
        </p>
      )}
      {verification?.original_surface_deviation && (
        <p>
          Đã đo thêm STEP sau nhập lại so với lưới gốc: sai lệch lớn nhất lấy
          mẫu{" "}
          {number(
            Math.max(
              verification.original_surface_deviation.source_to_result.max,
              verification.original_surface_deviation.result_to_source.max,
            ),
          )}{" "}
          {unit} trên bản tessellation.
        </p>
      )}
      <small>
        File gốc được giữ nguyên. Kiểm tra sai lệch và cạnh sắc dùng lấy mẫu,
        không phải chứng nhận toàn bề mặt liên tục.
      </small>
    </section>
  );
}
