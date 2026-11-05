# Bề mặt cong · v0.2

## Những gì được phục dựng

| Nhóm | Cách nhận dạng và dựng | Ví dụ |
|---|---|---|
| Cầu | Bình phương tối thiểu các đỉnh, dựng sphere OCCT | Icosphere đủ mịn → 1 mặt cầu |
| Xuyến | Tìm trục, fit đường tròn trong mặt phẳng kinh tuyến | Vòng xuyến đầy đủ → 1 mặt torus; loại horn/spindle |
| Tròn xoay | Phát hiện các vòng đầy đủ, nối thành biên dạng kinh tuyến đơn, quay 360° | Trụ, nón/côn cụt, ống rỗng, trục bậc, vát cạnh đồng tâm |
| Khối đùn | Hai mặt đầu song song, vòng biên kín, fit đường tròn/cung tròn | Tấm có nhiều lỗ lệch tâm, đường bao có góc bo tròn |

Nhánh khối đùn giữ các lỗ như vòng trong của face, không lấp chúng. Các đoạn thẳng tạo mặt phẳng, cung tròn tạo mặt trụ. Hướng và vị trí bất kỳ được xét qua các trục ứng viên từ tọa độ đỉnh và pháp tuyến mặt. Trục PCA không được coi là kết quả đúng cho tới khi phép dựng vượt qua các kiểm tra.

Đây là reconstruction hình học theo từng thành phần liên thông, không phải mạng AI, không phải công cụ tái dựng tự do mọi bề mặt STL. Nhánh khối đùn có thể tạo mặt trụ cục bộ trên một chi tiết có nhiều mặt phẳng/lỗ, nhưng không tự phát hiện mọi mảnh trụ trên chi tiết 3D bất kỳ.

## Các cổng kiểm tra

1. Chỉ nạp thành phần lưới kín, hướng nhất quán. Giữ nguyên file nguồn; sửa cơ bản như bản 0.1.
2. Dung sai fitting phải hữu hạn, lớn hơn 0, không vượt 1% đường chéo từng thành phần. Mốc này chặn dung sai quá rộng; không phải độ chính xác đã được chứng nhận.
3. Solid ứng viên phải hợp lệ theo OCCT, có 1 solid và thể tích dương. Biên dạng kinh tuyến không tự cắt; xuyến không tự giao.
4. Euler characteristic của mesh phải khớp nhóm primitive/profile: giữ topology lỗ của các dạng được hỗ trợ. Đây là một kiểm tra topology, không chứng minh đầy đủ tương đương hình học.
5. Đo mesh → CAD tại tất cả đỉnh, tâm tam giác và trung điểm cạnh. Tròn xoay/cầu/xuyến dùng hàm khoảng cách giải tích; khối đùn dùng khoảng cách OCCT tới shell thực, không dùng khoảng cách tới thể tích solid (vì điểm bên trong solid có thể cho khoảng cách bằng 0).
6. Đo CAD → mesh bằng điểm chính xác trên bề mặt giải tích: trên mặt cong, các đường biên và mặt đầu. Dùng point-to-triangle với R-tree, xử lý theo chunk để tránh một mảng khoảng cách khổng lồ. Mỗi hướng lưu max/RMS/p95/số điểm/tọa độ điểm xấu nhất.
7. Sai lệch hai hướng và thay đổi bounding box phải không vượt dung sai; thay đổi thể tích tương đối không vượt cấu hình (mặc định 2%, tối đa 5%). Vì làm tròn các dây cung STL thành cung thật thường làm thay đổi thể tích, không áp dụng ngưỡng `1e-5` của gộp mặt phẳng cho bước phục dựng cong.
8. Xuất STEP AP214 rồi nhập lại: kiểm tra solid, thể tích/bounds giữa CAD trước xuất và STEP (ngưỡng round-trip vẫn chặt), loại/số mặt. Sau đó đo thêm tối đa 257 điểm nguồn mỗi thành phần đã nhận dạng tới **shell STEP đã nhập lại**, gồm điểm sai lệch nguồn lớn nhất trước xuất.

Các điểm bề mặt và lưới được lấy mẫu có tính quyết định; **max đo được không phải cận Hausdorff chứng nhận trên bề mặt liên tục**. Chi tiết nhỏ nằm giữa các điểm kiểm tra có thể bị bỏ sót; kiểm tra và xác nhận file thực tế trước khi sản xuất. STL thô với ít cạnh có thể bị từ chối dù đỉnh cùng nằm trên một mặt trụ lý tưởng, vì phần giữa các đỉnh vẫn lệch lớn.

## Bảo toàn đặc trưng

- Không làm mịn/remesh STL, không tự vá lỗ.
- Giữ các vai, bậc và cạnh vát trong biên dạng tròn xoay; chỉ bỏ nút thẳng hàng và làm tròn sai số lượng tử dưới ngưỡng phân cụm.
- Với nhánh tròn xoay/khối đùn, độ phân giải phân cụm là `max(diagonal * 2e-6, fit_tolerance * 0.005)` theo đơn vị nguồn. Có thể snap các tọa độ rất gần nhau trong phạm vi này; các kiểm tra hình học sau dựng vẫn bắt buộc.
- Không thay chi tiết bất đối xứng bằng khối tròn xoay khi phép đo không đạt.
- Nhánh tròn xoay yêu cầu vòng góc đầy đủ với ít nhất 12 vị trí mẫu và khoảng hở góc tối đa 45°. Giới hạn 256 nút trước rút gọn và 64 nút biên dạng sau rút gọn.
- Nhánh khối đùn yêu cầu cùng tiết diện, độ sâu không đổi và các đỉnh thuộc hai mặt đầu trong độ phân giải. Giới hạn tổng 1.024 đỉnh vòng biên, tối đa 80 đoạn/cung sau fitting; các trường hợp lớn/phức tạp hơn giữ faceted.

## Cấu trúc báo cáo

`curve_reconstruction` ghi chế độ, dung sai, giới hạn thể tích và `components` theo index từ 0. Mỗi thành phần có `accepted`, `reason`, số mặt nguồn, vùng bao và `attempts` bị từ chối. Thành phần được nhận có tham số hình học, thống kê sai lệch, `surface_types`, thể tích tương đối và số mặt CAD. `reimported_step_distances` ghi phép kiểm tra tới STEP thật sau round-trip.

`surface_types` cấp cao là số mặt **đọc từ STEP**, ví dụ `{"plane": 2, "cylinder": 1}` cho trụ đặc. Các tam giác WebGL chỉ là tessellation hiển thị.

## Chưa hỗ trợ

NURBS tự do/loft, organic mesh bất kỳ, fillet chuyển tiếp không thuộc tiết diện hỗ trợ, lỗ xiên/lỗ mù/độ sâu thay đổi, trimming và khâu mọi mảnh cong cục bộ, fitting bền vững với scan nhiễu lớn, kiểm tra tự giao đầy đủ và cận sai lệch liên tục. Không có checkpoint AI hoặc yêu cầu GPU. Trong `auto`, báo cáo nêu rõ thành phần nào vẫn còn faceted; trong `required`, các trường hợp không đạt bị chặn xuất.

Nguồn API: [OCCT rotational sweep](https://www.occt3d.com/dev/doc/overview/html/occt_user_guides__modeling_algos.html), [trimesh proximity](https://trimesh.org/trimesh.proximity.html), [trimesh sampling](https://trimesh.org/trimesh.sample.html).
