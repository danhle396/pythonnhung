// Sinh slide bảo vệ đồ án: docs/report/slides_bao_ve.pptx
//   cd tools/slides && npm install && node build_slides.js
// Số liệu lấy từ docs/report/results_*.md (đã chép vào hằng bên dưới — cập nhật khi huấn luyện lại).
const path = require('path');
const pptxgen = require('pptxgenjs');

const ROOT = path.resolve(__dirname, '..', '..');
const FIG = p => path.join(ROOT, 'docs', 'report', 'figures', p);
const OUT = path.join(ROOT, 'docs', 'report', 'slides_bao_ve.pptx');

// ---- bảng màu: xanh biển sâu (thời tiết, Đà Nẵng) + hổ phách (cảnh báo gas)
const C = {
  ink: '0F1B2D', deep: '0B4F6C', teal: '1B7F8E', mist: 'E6F0F3', paper: 'FFFFFF',
  amber: 'F2A541', red: 'C0392B', green: '2E7D32', yellow: 'F4C430', orange: 'E67E22',
  grey: '5B6B7A', light: 'C9D6DE',
};
const LV = [C.green, C.yellow, C.orange, C.red];
const HEAD = 'Arial';
const BODY = 'Calibri';

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.33 x 7.5 in
pres.title = 'Trạm quan trắc môi trường AIoT — VKU';
pres.author = 'Nhóm đồ án VKU';
pres.subject = 'Dự báo thời tiết ngắn hạn và cảnh báo khí gas/khói đa cấp, AI lai Edge–Cloud';

const W = 13.333, H = 7.5, M = 0.6;

// ---- layout: tiêu đề nội dung (sáng), section (tối)
pres.defineSlideMaster({
  title: 'CONTENT', background: {color: C.paper},
  objects: [
    {placeholder: {options: {name: 'title', type: 'title', x: M, y: 0.35, w: W - 2 * M, h: 0.85,
      fontFace: HEAD, fontSize: 30, bold: true, color: C.ink, valign: 'middle', align: 'left', margin: 0}, text: ''}},
    {text: {text: 'VKU · Trạm quan trắc AIoT', options: {x: M, y: H - 0.42, w: 6, h: 0.3, fontFace: BODY,
      fontSize: 10, color: C.grey, margin: 0}}},
  ],
  slideNumber: {x: W - M - 0.6, y: H - 0.42, w: 0.6, h: 0.3, fontFace: BODY, fontSize: 10, color: C.grey, align: 'right'},
});
pres.defineSlideMaster({
  title: 'DARK', background: {color: C.ink},
  objects: [
    {placeholder: {options: {name: 'title', type: 'title', x: M, y: 2.3, w: W - 2 * M, h: 1.4,
      fontFace: HEAD, fontSize: 40, bold: true, color: C.paper, valign: 'bottom', align: 'left', margin: 0}, text: ''}},
    {placeholder: {options: {name: 'body', type: 'body', x: M, y: 3.85, w: W - 2 * M, h: 1.6,
      fontFace: BODY, fontSize: 18, color: C.light, valign: 'top', margin: 0}, text: ''}},
  ],
});

// giữ số kiểu '26 000' trên một dòng
const nb = t => typeof t === 'string' ? t.replace(/(\d) (\d{3})/g, '$1 $2') : t;
let section = null;
function slide(title, sec, master = 'CONTENT') {
  if (sec && sec !== section) { pres.addSection({title: sec}); section = sec; }
  const s = pres.addSlide({masterName: master, sectionTitle: section});
  if (title) s.addText(title, {placeholder: 'title'});
  return s;
}
function text(s, t, o) { s.addText(nb(t), Object.assign({isTextBox: true, fontFace: BODY, fontSize: 16, color: C.ink, margin: 0, valign: 'top'}, o)); }
function card(s, x, y, w, h, fill = C.mist, name) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x, y, w, h, rectRadius: 0.12, fill: {color: fill}, line: {color: fill}, objectName: name});
}
function dot(s, x, y, d, color, label) {
  s.addShape(pres.shapes.OVAL, {x, y, w: d, h: d, fill: {color}, line: {color}});
  if (label !== undefined) s.addText(String(label), {x, y, w: d, h: d, isTextBox: true, align: 'center', valign: 'middle',
    fontFace: HEAD, bold: true, fontSize: d * 22, color: C.paper, margin: 0});
}
function stat(s, x, y, w, big, small, color = C.deep) {
  text(s, big, {x, y, w, h: 0.95, fontFace: HEAD, fontSize: 44, bold: true, color, valign: 'bottom'});
  text(s, small, {x, y: y + 1.0, w, h: 0.7, fontSize: 14, color: C.grey});
}
function bullets(s, items, o) {
  s.addText(items.map((t, i) => ({text: nb(t), options: {bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6}})),
    Object.assign({isTextBox: true, fontFace: BODY, fontSize: 16, color: C.ink, margin: 0, valign: 'top'}, o));
}
function img(s, file, x, y, w, h, alt) { s.addImage({path: FIG(file), x, y, w, h, altText: alt}); }
const tableOpts = (x, y, w, colW, rowH = 0.5) => ({x, y, w, colW, rowH, fontFace: BODY, fontSize: 14, color: C.ink, border: {type: 'solid', pt: 0.5, color: C.light},
  margin: [0.04, 0.08, 0.04, 0.08], valign: 'middle'});
const th = t => ({text: t, options: {bold: true, color: C.paper, fill: {color: C.deep}}});

// =============================================================== 1. Tiêu đề
{
  const s = slide(null, 'Mở đầu', 'DARK');
  s.addText('Trạm quan trắc môi trường AIoT', {placeholder: 'title'});
  s.addText([
    {text: 'Dự báo thời tiết ngắn hạn và cảnh báo sớm khí gas/khói 4 cấp với AI lai Edge–Cloud', options: {breakLine: true}},
    {text: 'ESP32 · MQTT · FastAPI · TimescaleDB · thư viện ML tự viết bằng NumPy', options: {color: C.amber, breakLine: true}},
    {text: 'VKU — Đại học Đà Nẵng · 11/2026', options: {fontSize: 14}},
  ], {placeholder: 'body'});
  [0, 1, 2, 3].forEach(i => dot(s, M + i * 0.55, 1.4, 0.38, LV[i]));
  s.addNotes('Giới thiệu đề tài: một trạm ESP32 vừa dự báo thời tiết ngắn hạn tại VKU vừa cảnh báo khí gas/khói 4 cấp. Điểm nhấn: AI lai edge–cloud và toàn bộ ML tự cài đặt.');
}

// =============================================================== 2. Bối cảnh
{
  const s = slide('Bối cảnh: mưa nhiều và nguy cơ gas trong nhà', 'Mở đầu');
  stat(s, M, 1.5, 3.6, '62–66 %', 'số giờ có mưa trong tháng 10 và 12 tại VKU (Open-Meteo 2021–2025)');
  stat(s, M + 4.1, 1.5, 3.6, '668 mm', 'lượng mưa trung bình tháng 10 — thời tiết đổi nhanh theo giờ');
  stat(s, M + 8.2, 1.5, 3.6, '≈ 2 %', 'giới hạn nổ dưới (LEL) của LPG ≈ 20 000 ppm', C.red);
  card(s, M, 4.1, W - 2 * M, 2.05, C.mist);
  text(s, 'Vấn đề', {x: M + 0.3, y: 4.3, w: 5, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: C.deep});
  bullets(s, [
    'Dự báo công cộng có độ phân giải thô, không phản ánh vi khí hậu tại một điểm.',
    'Đầu báo gas giá rẻ chỉ có 1 ngưỡng cố định: dễ báo nhầm, không báo từ xa, không biết rò rỉ chậm.',
    'Thiết bị IoT phụ thuộc mạng: mất Wi-Fi là mất cảnh báo.',
  ], {x: M + 0.3, y: 4.8, w: W - 2 * M - 0.6, h: 1.6});
  s.addNotes('Số liệu khí hậu tính từ 43 824 giờ Open-Meteo tại toạ độ VKU. Nêu ba vấn đề mà hệ thống giải quyết.');
}

// =============================================================== 3. Mục tiêu
{
  const s = slide('Mục tiêu và KPI', 'Mở đầu');
  const goals = [
    ['Trạm 5 cảm biến', 'DHT22, BMP280, BH1750, YL-83, MQ-2 gửi MQTT ổn định ≥ 72 h'],
    ['Cảnh báo 4 cấp', 'Tại edge: hysteresis, debounce, chạy khi mất mạng, nút tắt còi'],
    ['Dự báo 1 / 3 / 6 giờ', 'Nhiệt, ẩm, áp suất, mưa — vượt baseline persistence'],
    ['Cloud + dashboard', 'Lưu trữ, leo thang, Telegram/Email, cấu hình từ xa'],
  ];
  const cw = (W - 2 * M - 3 * 0.3) / 4;
  goals.forEach(([t, d], i) => {
    const x = M + i * (cw + 0.3);
    card(s, x, 1.5, cw, 2.6);
    dot(s, x + 0.3, 1.75, 0.55, C.deep, i + 1);
    text(s, t, {x: x + 0.3, y: 2.45, w: cw - 0.6, h: 0.5, fontFace: HEAD, fontSize: 17, bold: true});
    text(s, d, {x: x + 0.3, y: 3.0, w: cw - 0.6, h: 1.0, fontSize: 14, color: C.grey});
  });
  card(s, M, 4.5, W - 2 * M, 1.75, 'FFF4E0');
  text(s, 'Ràng buộc', {x: M + 0.3, y: 4.7, w: 4, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: C.orange});
  text(s, 'Không dùng thư viện học máy (scikit-learn, XGBoost, PyTorch, TensorFlow…). Mọi mô hình — CART, Random Forest, '
    + 'Gradient Boosting, Logistic, Holt-Winters, Isolation Forest, CUSUM, MLP, GRU — tự cài đặt bằng NumPy trong thư viện mlcore.',
    {x: M + 0.3, y: 5.2, w: W - 2 * M - 0.6, h: 1.2, fontSize: 16});
  s.addNotes('Bốn mục tiêu và ràng buộc quan trọng nhất: tự viết toàn bộ ML.');
}

// =============================================================== 4. Kiến trúc
{
  const s = slide('Kiến trúc AI lai Edge–Cloud', 'Thiết kế');
  // edge
  card(s, M, 1.4, 4.6, 5.1, C.mist, 'edge');
  text(s, 'EDGE — ESP32', {x: M + 0.25, y: 1.55, w: 4, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: C.deep});
  const eb = ['5 cảm biến · lọc median + EWMA', '10 feature cửa sổ 10–60 s', 'Rule 4 cấp ∥ Random Forest 10 cây',
    'level = max(rule, model)', 'LED · còi · quạt · OLED', 'Đệm offline LittleFS · seq'];
  eb.forEach((t, i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x: M + 0.25, y: 2.05 + i * 0.7, w: 4.1, h: 0.56, rectRadius: 0.08,
      fill: {color: i === 3 ? C.amber : C.paper}, line: {color: C.light}});
    text(s, t, {x: M + 0.4, y: 2.05 + i * 0.7, w: 3.8, h: 0.56, fontSize: 14, valign: 'middle', bold: i === 3});
  });
  // broker
  const bx = M + 4.95;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x: bx, y: 3.2, w: 2.3, h: 1.5, rectRadius: 0.2, fill: {color: C.deep}, line: {color: C.deep}});
  text(s, 'Mosquitto\nMQTT', {x: bx, y: 3.25, w: 2.3, h: 0.85, fontFace: HEAD, fontSize: 17, bold: true, color: C.paper, align: 'center', valign: 'middle'});
  text(s, 'auth · ACL · LWT · retain', {x: bx, y: 4.05, w: 2.3, h: 0.5, fontSize: 12, color: C.light, align: 'center'});
  s.addShape(pres.shapes.LINE, {x: M + 4.6, y: 3.95, w: 0.35, h: 0, line: {color: C.deep, width: 2, beginArrowType: 'triangle', endArrowType: 'triangle'}});
  s.addShape(pres.shapes.LINE, {x: bx + 2.3, y: 3.95, w: 0.35, h: 0, line: {color: C.deep, width: 2, beginArrowType: 'triangle', endArrowType: 'triangle'}});
  text(s, 'telemetry · alert · status\ncmd · config · forecast', {x: bx - 0.2, y: 4.85, w: 2.7, h: 0.7, fontSize: 12, color: C.grey, align: 'center'});
  // cloud
  const cx = bx + 2.65;
  card(s, cx, 1.4, W - M - cx, 5.1, C.mist, 'cloud');
  text(s, 'CLOUD — Docker Compose', {x: cx + 0.25, y: 1.55, w: 4.5, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: C.deep});
  const cb = [['Ingest', 'validate · chống trùng · ghi lô'], ['Alert service', 'leo thang 10 phút · Isolation Forest · nhắc lại'],
    ['Forecast service', 'GBDT mlcore + bias correction'], ['TimescaleDB', 'hypertable · continuous aggregate'],
    ['API + Dashboard', 'JWT · WebSocket · Streamlit · Grafana'], ['Thông báo', 'Telegram · Email · ack inline']];
  const cwid = W - M - cx - 0.5;
  cb.forEach(([t, d], i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {x: cx + 0.25, y: 2.05 + i * 0.7, w: cwid, h: 0.56, rectRadius: 0.08, fill: {color: C.paper}, line: {color: C.light}});
    s.addText([{text: t + '  ', options: {bold: true}}, {text: d, options: {color: C.grey, fontSize: 13}}],
      {x: cx + 0.4, y: 2.05 + i * 0.7, w: cwid - 0.3, h: 0.56, isTextBox: true, fontFace: BODY, fontSize: 14, color: C.ink, valign: 'middle', margin: 0});
  });
  s.addNotes('Edge: quyết định an toàn trong dưới 1 giây và độc lập mạng. Cloud: ngữ cảnh dài, dự báo, thông báo, lưu trữ. MQTT nối hai phía.');
}

// =============================================================== 5. Phần cứng & MQTT
{
  const s = slide('Phần cứng và giao thức MQTT', 'Thiết kế');
  const rows = [[th('Linh kiện'), th('Chân ESP32'), th('Ghi chú')],
    ['BMP280 · BH1750 · OLED', 'I²C 21/22', '0x76 · 0x23 · 0x3C'],
    ['DHT22', 'GPIO 4', 'chu kỳ 2 s'],
    ['YL-83', 'AO 34 · nguồn 18', 'cấp nguồn khi đọc'],
    ['MQ-2', 'AO 32 · DO 33', 'phân áp 10k/20k'],
    ['Còi · LED X/V/Đ', '25 · 26/27/14', ''],
    ['Nút · relay quạt', '13 · 23', 'mute 5 phút']];
  s.addTable(rows, tableOpts(M, 1.45, 6.2, [2.4, 1.9, 1.9], 0.52));
  const r2 = [[th('Topic vku/aiot/{id}/…'), th('QoS'), th('Retain')],
    ['telemetry (10 s, 1 s khi cảnh báo)', '0', ''], ['alert · nowcast', '0', 'nowcast'], ['status (LWT offline)', '0', '✔'],
    ['cmd (mute, calibrate, ota…)', '1', ''], ['config (có phiên bản + ack)', '1', '✔'], ['forecast → OLED', '1', '✔']];
  s.addTable(r2, tableOpts(M + 6.6, 1.45, W - 2 * M - 6.6, [3.6, 0.8, 1.13], 0.52));
  card(s, M, 5.45, W - 2 * M, 1.1, 'FFF4E0');
  text(s, 'PubSubClient chỉ publish QoS 0 → tin cậy ở tầng ứng dụng: số thứ tự seq + đệm offline LittleFS 2 000 bản ghi + '
    + 'backend chống trùng theo khoá (device_id, ts, seq).', {x: M + 0.3, y: 5.55, w: W - 2 * M - 0.6, h: 0.9, fontSize: 16, valign: 'middle'});
  s.addNotes('Sơ đồ chân từ firmware/include/config.h. ACL: mỗi thiết bị chỉ ghi topic của chính nó.');
}

// =============================================================== 6. Cảnh báo 4 cấp
{
  const s = slide('Cảnh báo 4 cấp tại edge', 'Thiết kế');
  const lv = [['0', 'Bình thường', 'ppm < 300', 'LED xanh'], ['1', 'Chú ý', 'ppm ≥ 300 hoặc dốc ≥ 15 ppm/s', 'LED vàng · log'],
    ['2', 'Cảnh báo', 'ppm ≥ 1 000', 'đỏ nháy · còi · quạt · Telegram'],
    ['3', 'Nguy hiểm', 'ppm ≥ 2 000 hoặc ≥ 1 000 + nhiệt tăng ≥ 1 °C/phút', 'còi liên tục · Telegram + Email · nhắc mỗi phút']];
  lv.forEach(([n, name, cond, act], i) => {
    const y = 1.45 + i * 1.1;
    card(s, M, y, 7.6, 0.95);
    dot(s, M + 0.15, y + 0.2, 0.56, LV[i], n);
    text(s, name, {x: M + 0.9, y, w: 1.7, h: 0.95, fontFace: HEAD, fontSize: 16, bold: true, valign: 'middle'});
    text(s, cond, {x: M + 2.6, y, w: 2.5, h: 0.95, fontSize: 13, valign: 'middle'});
    text(s, act, {x: M + 5.15, y, w: 2.35, h: 0.95, fontSize: 13, color: C.grey, valign: 'middle'});
  });
  const x2 = M + 8.0, w2 = W - M - x2;
  card(s, x2, 1.45, w2, 4.25, C.mist);
  text(s, 'Chống dao động & an toàn', {x: x2 + 0.25, y: 1.6, w: w2 - 0.5, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: C.deep});
  bullets(s, ['Hysteresis 15 %: hạ cấp khi ppm < 0,85 × ngưỡng', 'Debounce: lên 3 mẫu, xuống 5 mẫu; cấp 3 lên ngay',
    'Fusion = max(rule, model): model chỉ báo sớm hơn, không hạ cấp', 'Cloud leo thang khi ppm tăng đều 10 phút hoặc Isolation Forest báo bất thường'],
  {x: x2 + 0.25, y: 2.1, w: w2 - 0.5, h: 3.0, fontSize: 14});
  text(s, '10 feature: gas_ppm · Rs/R0 · slope10 · std30 · dev_base · temp · dtemp/phút · hum · dhum/phút · lux_rel',
    {x: M, y: 6.05, w: W - 2 * M, h: 0.5, fontSize: 14, color: C.grey, italic: true});
  s.addNotes('Ngưỡng mặc định có thể đổi từ xa qua topic config. Hybrid lấy max để ưu tiên không bỏ sót.');
}

// =============================================================== 7. mlcore
{
  const s = slide('mlcore — thư viện học máy tự viết bằng NumPy', 'Học máy');
  const mods = [['Cây & tổ hợp', 'CART histogram · Random Forest · GBDT (MSE, log-loss) · early stopping'],
    ['Tuyến tính & chuỗi', 'OLS/Ridge · Logistic · Holt-Winters damped'], ['Bất thường', 'Isolation Forest · CUSUM · z-score theo giờ'],
    ['Mạng nơ-ron', 'MLP · GRU + BPTT · SGD/Momentum/Adam · clipping'], ['Đánh giá & giải thích', 'MAE/RMSE · F1 · ROC-AUC Mann–Whitney · permutation importance'],
    ['Triển khai', 'serialize JSON/.npz · registry · export_c → gas_model.h']];
  const cw = (W - 2 * M - 2 * 0.3) / 3;
  mods.forEach(([t, d], i) => {
    const x = M + (i % 3) * (cw + 0.3), y = 1.45 + Math.floor(i / 3) * 1.75;
    card(s, x, y, cw, 1.5);
    text(s, t, {x: x + 0.25, y: y + 0.15, w: cw - 0.5, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: C.deep});
    text(s, d, {x: x + 0.25, y: y + 0.6, w: cw - 0.5, h: 0.85, fontSize: 14});
  });
  stat(s, M, 5.0, 3.6, '42', 'unit test pass (dữ liệu đồ chơi, round-trip, không rò rỉ tương lai)');
  stat(s, M + 4.1, 5.0, 3.6, '< 1e-5', 'sai số gradient check cho Logistic, MLP, GRU');
  stat(s, M + 8.2, 5.0, 3.6, '≈ 2 500', 'dòng code NumPy, giao diện fit / predict / to_dict');
  s.addNotes('Mọi mô hình triển khai đều nạp bằng mlcore.serialize.load_model; requirements không chứa thư viện ML.');
}

// =============================================================== 8. Toán GBDT
{
  const s = slide('Gradient Boosting trên histogram (dạng Newton)', 'Học máy');
  card(s, M, 1.45, 6.3, 4.9);
  const f = [
    ['Gradient / hessian', 'MSE: g = F − y, h = 1\nLog-loss: g = p − y, h = p(1 − p)'],
    ['Gain khi chia nút', 'G_L²/(H_L+λ) + G_R²/(H_R+λ) − G²/(H+λ)'],
    ['Giá trị lá (bước Newton)', 'w* = −G / (H + λ)'],
    ['Cập nhật', 'F_m(x) = F_{m−1}(x) + η · f_m(x)'],
  ];
  f.forEach(([t, e], i) => {
    text(s, t, {x: M + 0.3, y: 1.6 + i * 1.18, w: 5.7, h: 0.35, fontSize: 14, bold: true, color: C.deep});
    text(s, e, {x: M + 0.3, y: 1.95 + i * 1.18, w: 5.7, h: 0.75, fontFace: 'Cambria', fontSize: 17});
  });
  const x2 = M + 6.7, w2 = W - M - x2;
  text(s, 'Tăng tốc', {x: x2, y: 1.5, w: w2, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: C.deep});
  bullets(s, ['Rời rạc hoá mỗi feature ≤ 64 bin theo phân vị → tìm ngưỡng O(F·B) thay vì sắp xếp',
    'np.bincount theo (nút × bin) — histogram cả tầng trong một lệnh',
    'Trừ histogram: con lớn = cha − con nhỏ',
    'Subsample hàng + early stopping trên validation'], {x: x2, y: 2.0, w: w2, h: 2.6, fontSize: 15});
  card(s, x2, 4.75, w2, 1.6, 'FFF4E0');
  text(s, 'GBDT nhiệt độ 1 h: 123 cây, huấn luyện 7,7 s trên 26 000 giờ, suy luận 17,6 µs/mẫu', {x: x2 + 0.25, y: 4.9, w: w2 - 0.5, h: 1.3, fontSize: 16, valign: 'middle'});
  s.addNotes('Cùng một cây hồi quy dùng cho CART-MSE (g = −y, h = 1, λ = 0) và GBDT. Đây là công thức của XGBoost.');
}

// =============================================================== 9. Edge model → C
{
  const s = slide('Từ Python tới ESP32: xuất Random Forest sang C', 'Học máy');
  const steps = [['Huấn luyện', 'train_gas_edge.py\nRF 10 cây, sâu 6'], ['Xuất C', 'export_c.py → gas_model.h\nmảng const, không đệ quy'],
    ['So khớp', 'g++ + Unity test\n490 mẫu, lệch 0'], ['Nạp ESP32', 'TaskEdgeAI 1 Hz\nfusion với rule']];
  const sw = (W - 2 * M - 3 * 0.45) / 4;
  steps.forEach(([t, d], i) => {
    const x = M + i * (sw + 0.45);
    card(s, x, 1.5, sw, 1.9, i === 2 ? 'FFF4E0' : C.mist);
    dot(s, x + 0.25, 1.7, 0.5, C.deep, i + 1);
    text(s, t, {x: x + 0.9, y: 1.7, w: sw - 1.1, h: 0.5, fontFace: HEAD, fontSize: 17, bold: true, valign: 'middle'});
    text(s, d, {x: x + 0.25, y: 2.35, w: sw - 0.5, h: 0.95, fontSize: 14, color: C.grey});
    if (i < 3) s.addShape(pres.shapes.LINE, {x: x + sw + 0.05, y: 2.45, w: 0.35, h: 0, line: {color: C.deep, width: 2, endArrowType: 'triangle'}});
  });
  stat(s, M, 3.9, 2.9, '17 kB', 'flash cho 10 cây (1 016 nút)');
  stat(s, M + 3.1, 3.9, 2.9, '656 B', 'RAM lúc chạy');
  stat(s, M + 6.2, 3.9, 2.9, '0', 'lệch lớp C ↔ Python', C.green);
  stat(s, M + 9.3, 3.9, 2.9, '48,9 %', 'flash firmware (RAM 14,9 %)');
  text(s, 'Feature quan trọng: Rs/R0 0,33 · dtemp/phút 0,21 · ppm 0,17 · độ lệch nền 0,12 · độ dốc 10 s 0,11',
    {x: M, y: 6.0, w: W - 2 * M, h: 0.4, fontSize: 14, italic: true, color: C.grey});
  s.addNotes('Bộ xuất C tự viết thay cho emlearn. Unity test chạy cả native lẫn trên ESP32 thật để đo micro-giây.');
}

// =============================================================== 10. Backend
{
  const s = slide('Cloud: alert service và forecast service', 'Hệ thống');
  const x2 = M + 6.3;
  card(s, M, 1.45, 5.95, 3.5);
  text(s, 'Alert service', {x: M + 0.3, y: 1.6, w: 5, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: C.deep});
  bullets(s, ['Cấp 1: log · cấp 2: Telegram · cấp 3: Telegram + Email', 'Cooldown theo (thiết bị, cấp); nhắc lại cấp 3 mỗi phút tới khi ack',
    'Leo thang: độ dốc ppm 10 phút, Isolation Forest → cmd escalate', 'Offline > 60 s hoặc LWT → cảnh báo device_offline',
    'Ack qua dashboard hoặc nút inline Telegram'], {x: M + 0.3, y: 2.15, w: 5.4, h: 2.75, fontSize: 15});
  card(s, x2, 1.45, W - M - x2, 3.5);
  text(s, 'Forecast service (10 phút)', {x: x2 + 0.3, y: 1.6, w: 6, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: C.deep});
  bullets(s, ['Pretrain trên 5 năm Open-Meteo tại VKU', 'Bias correction trạm → Open-Meteo (Ridge; chỉ hiệu chỉnh độ lệch khi tương quan kém)',
    'Dự phòng: dữ liệu trạm → Open-Meteo 4 ngày → persistence', 'Khoảng tin cậy 95 %: ŷ ± 1,96 · RMSE_test',
    'Publish forecast (retain) → OLED; tin tóm tắt 6 giờ sáng'], {x: x2 + 0.3, y: 2.15, w: W - M - x2 - 0.6, h: 2.75, fontSize: 15});
  stat(s, M, 5.1, 2.9, '≈ 0,45 s', 'thiết bị phát alert → backend gửi thông báo');
  stat(s, M + 3.1, 5.1, 2.9, '12', 'dự báo mỗi lượt (4 biến × 3 tầm)');
  stat(s, M + 6.2, 5.1, 2.9, '0,2 s', 'thời gian một lượt dự báo trong Docker');
  stat(s, M + 9.3, 5.1, 2.9, '15', 'test backend, gồm integration MQTT');
  s.addNotes('FastAPI + SQLAlchemy 2 + APScheduler. 15 test backend gồm integration test với Mosquitto thật.');
}

// =============================================================== 11. Dashboard
{
  const s = slide('Dashboard: realtime, dự báo, cảnh báo, cấu hình', 'Hệ thống');
  const iw = (W - 2 * M - 0.3) / 2;
  const h1 = iw * 570 / 1250, h2 = iw * 630 / 1250;
  img(s, 'slides/overview_crop.png', M, 1.4, iw, h1, 'Trang tổng quan dashboard');
  img(s, 'slides/forecast_crop.png', M + iw + 0.3, 1.4, iw, h2, 'Trang dự báo dashboard');
  s.addShape(pres.shapes.RECTANGLE, {x: M, y: 1.4, w: iw, h: h1, fill: {type: 'none'}, line: {color: C.light, width: 1}});
  s.addShape(pres.shapes.RECTANGLE, {x: M + iw + 0.3, y: 1.4, w: iw, h: h2, fill: {type: 'none'}, line: {color: C.light, width: 1}});
  text(s, 'Tổng quan: cấp cảnh báo, số đo, dự báo, cảnh báo gần đây', {x: M, y: 1.5 + h1, w: iw, h: 0.4, fontSize: 13, color: C.grey});
  text(s, 'Dự báo: thực tế vs dự báo + khoảng tin cậy 95 %, xác suất mưa', {x: M + iw + 0.3, y: 1.5 + h2, w: iw, h: 0.4, fontSize: 13, color: C.grey});
  card(s, M, 5.75, W - 2 * M, 0.75);
  text(s, 'Streamlit 6 trang (Tổng quan · Biểu đồ · Dự báo · Cảnh báo + ack · Thiết bị: lệnh & cấu hình · Mô hình) + Grafana provision sẵn đọc TimescaleDB',
    {x: M + 0.25, y: 5.75, w: W - 2 * M - 0.5, h: 0.75, fontSize: 15, valign: 'middle'});
  s.addNotes('Ảnh chụp từ stack Docker chạy với simulator. Trang Cảnh báo có nút xác nhận.');
}

// =============================================================== 12. Kết quả dự báo
{
  const s = slide('Dự báo: GBDT tốt nhất ở mọi biến và mọi tầm', 'Kết quả');
  const models = ['Persistence', 'Holt-Winters', 'Ridge', 'GBDT', 'GRU (NumPy)'];
  const temp = {Persistence: [0.593, 1.559, 2.759], 'Holt-Winters': [0.422, 0.821, 0.925], Ridge: [0.348, 0.690, 0.837], GBDT: [0.299, 0.543, 0.688], 'GRU (NumPy)': [0.310, 0.556, 0.714]};
  const hum = {Persistence: [2.968, 7.541, 13.210], 'Holt-Winters': [2.384, 4.299, 4.766], Ridge: [2.045, 3.822, 4.515], GBDT: [1.856, 3.244, 3.980], 'GRU (NumPy)': [1.932, 3.295, 4.052]};
  const colors = ['9AA5B1', 'F0B429', '3E7CB1', '0B6E4F', 'C75146'];
  const chartOpts = (title, x) => ({x, y: 1.4, w: 5.9, h: 3.9, barDir: 'col', barGrouping: 'clustered', chartColors: colors,
    showTitle: true, title, titleFontFace: BODY, titleFontSize: 14, titleColor: C.ink,
    showLegend: true, legendPos: 'b', legendFontFace: BODY, legendFontSize: 11,
    catAxisLabelFontFace: BODY, valAxisLabelFontFace: BODY, catAxisLabelColor: C.grey, valAxisLabelColor: C.grey,
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 11, valGridLine: {color: 'D9E2E8', size: 0.5}, catGridLine: {style: 'none'}});
  const data = d => models.map(m => ({name: m, labels: ['+1 h', '+3 h', '+6 h'], values: d[m]}));
  s.addChart(pres.charts.BAR, data(temp), chartOpts('MAE nhiệt độ (°C) — test 2025', M));
  s.addChart(pres.charts.BAR, data(hum), chartOpts('MAE độ ẩm (%RH) — test 2025', M + 6.25));
  stat(s, M, 5.4, 2.9, '0,30 °C', 'MAE nhiệt độ 1 h');
  stat(s, M + 3.1, 5.4, 2.9, '1,86 %', 'MAE độ ẩm 1 h');
  stat(s, M + 6.2, 5.4, 2.9, '0,839', 'F1 mưa 3 h (AUC 0,926)');
  stat(s, M + 9.3, 5.4, 2.9, '−75 %', 'MAE nhiệt 6 h so với persistence', C.green);
  s.addNotes('Train 2021–2023, validation 2024, test 2025, chia theo thời gian. 56 feature. GRU tự viết gần bằng GBDT nhưng huấn luyện lâu hơn nhiều.');
}

// =============================================================== 13. Dự báo minh hoạ
{
  const s = slide('Dự báo 3 giờ trong mùa mưa (1–14/11/2025)', 'Kết quả');
  img(s, 'forecast_3h_nov2025.png', M, 1.35, 7.4, 5.4, 'Đồ thị dự báo 3 giờ tháng 11 năm 2025');
  const x2 = M + 7.8, w2 = W - M - x2;
  card(s, x2, 1.45, w2, 5.0);
  text(s, 'Nhận xét', {x: x2 + 0.3, y: 1.6, w: w2 - 0.6, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: C.deep});
  bullets(s, ['GBDT bám chu kỳ ngày và các đợt lạnh, persistence trễ pha 3 giờ',
    'Feature mạnh nhất: hour_sin, temp_d1, xu hướng áp suất 3 h, góc thiên đỉnh — đúng trực giác vật lý',
    'Holt-Winters tốt hơn persistence nhưng không dùng được thông tin mưa/mây',
    'Mưa 6 h: GBDT F1 0,854 so với persistence 0,723'], {x: x2 + 0.3, y: 2.15, w: w2 - 0.6, h: 4.2, fontSize: 15});
  s.addNotes('Đường đen là thực tế, xanh lá là GBDT, cam là Ridge, chấm xanh là persistence.');
}

// =============================================================== 14. Rule/Model/Hybrid
{
  const s = slide('Cảnh báo khí: Rule / Model / Hybrid', 'Kết quả');
  const cats = ['Macro-F1', 'Recall ≥2 (mẫu)', 'Precision ≥2', 'Recall ≥2 (sự kiện)'];
  s.addChart(pres.charts.BAR, [
    {name: 'Rule', labels: cats, values: [0.569, 0.843, 0.615, 0.947]},
    {name: 'Model', labels: cats, values: [0.827, 0.895, 0.821, 1.0]},
    {name: 'Hybrid', labels: cats, values: [0.615, 0.920, 0.606, 1.0]}],
  {x: M, y: 1.4, w: 7.4, h: 4.6, barDir: 'col', barGrouping: 'clustered', chartColors: ['9AA5B1', '3E7CB1', '0B6E4F'],
    showLegend: true, legendPos: 'b', legendFontFace: BODY, legendFontSize: 12, valAxisMaxVal: 1, valAxisMinVal: 0,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 10, dataLabelFontFace: BODY, dataLabelFormatCode: '0.00', dataLabelColor: C.ink,
    catAxisLabelFontFace: BODY, valAxisLabelFontFace: BODY, catAxisLabelColor: C.grey, valAxisLabelColor: C.grey,
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 11, valGridLine: {color: 'D9E2E8', size: 0.5}, catGridLine: {style: 'none'}});
  const x2 = M + 7.8, w2 = W - M - x2;
  stat(s, x2, 1.4, w2, '19 → 12,3 s', 'độ trễ phát hiện cấp ≥ 2 (P95): Rule → Hybrid', C.green);
  stat(s, x2, 3.25, w2, '0,50', 'tỉ lệ báo động giả ≥ 2 trên sự kiện nhiễu (Hybrid) — đánh đổi để không bỏ sót', C.orange);
  card(s, M, 6.1, W - 2 * M, 0.6, 'FDECEA');
  text(s, '⚠ Dữ liệu MÔ PHỎNG (gas_sim.py, 151 324 mẫu 1 Hz) — sẽ huấn luyện lại với dữ liệu MQ-2 thật thu bằng label_logger.py',
    {x: M + 0.25, y: 6.1, w: W - 2 * M - 0.5, h: 0.6, fontSize: 14, color: C.red, valign: 'middle', bold: true});
  s.addNotes('Hybrid = max(rule, model) nên Recall cao nhất và trễ thấp nhất, nhưng gộp cả báo động giả. Cồn gây nhạy chéo MQ-2.');
}

// =============================================================== 15. Timeline
{
  const s = slide('End-to-end: kịch bản rò gas qua stack Docker', 'Kết quả');
  const tw = 4.0 * 1500 / 540;
  img(s, 'alert_timeline_sim.png', (W - tw) / 2, 1.3, tw, 4.0, 'Diễn biến ppm và cấp cảnh báo');
  const y = 5.45;
  const items = [['0→1→2→3→2→1', 'chuỗi cấp đúng thiết kế'], ['≈ 0,45 s', 'alert thiết bị → backend gửi thông báo'],
    ['Hysteresis', 'ppm < 2 000 nhưng giữ cấp 3 thêm vài giây'], ['LWT', 'tắt đột ngột → offline + device_offline']];
  const iw = (W - 2 * M - 3 * 0.3) / 4;
  items.forEach(([a, b], i) => {
    const x = M + i * (iw + 0.3);
    card(s, x, y, iw, 1.3);
    text(s, a, {x: x + 0.2, y: y + 0.12, w: iw - 0.4, h: 0.5, fontFace: HEAD, fontSize: 17, bold: true, color: C.deep});
    text(s, b, {x: x + 0.2, y: y + 0.65, w: iw - 0.4, h: 0.6, fontSize: 13, color: C.grey});
  });
  s.addNotes('Simulator chạy đúng logic edge (gas_edge.py giống hệt edge_ai.cpp). Dữ liệu đi qua Mosquitto, backend, TimescaleDB trong Docker.');
}

// =============================================================== 16. Hiệu năng
{
  const s = slide('Hiệu năng và triển khai', 'Kết quả');
  stat(s, M, 1.4, 2.9, '0 %', 'mất gói với 50 thiết bị × 1 msg/s, QoS 1', C.green);
  stat(s, M + 3.1, 1.4, 2.9, '3,4 ms', 'độ trễ broker P95 (Docker)');
  stat(s, M + 6.2, 1.4, 2.9, '100 %', 'bản ghi vào TimescaleDB');
  stat(s, M + 9.3, 1.4, 2.9, '≈ 10 %', 'CPU backend trung bình (1 lõi)');
  const rows = [[th('Kịch bản'), th('P50 / P95 / P99 (ms)'), th('CPU backend')],
    ['20 thiết bị, SQLite', '0,6 / 2,0 / 3,1', '54,5 %'], ['50 thiết bị, SQLite', '0,6 / 2,2 / 4,1', '61,4 %'],
    ['50 thiết bị, Docker + TimescaleDB', '1,7 / 3,4 / 4,4', '9,8 %']];
  s.addTable(rows, tableOpts(M, 3.55, 7.0, [3.2, 2.2, 1.6], 0.6));
  const x2 = M + 7.4, w2 = W - M - x2;
  card(s, x2, 3.55, w2, 2.9);
  text(s, 'docker compose up -d --build', {x: x2 + 0.25, y: 3.7, w: w2 - 0.5, h: 0.4, fontFace: 'Consolas', fontSize: 14, bold: true, color: C.deep});
  bullets(s, ['Mosquitto · TimescaleDB · backend · dashboard (+ Grafana)', 'Healthcheck + thứ tự khởi động', 'alembic upgrade head tự động',
    'Kiểm thử: 42 ML · 15 backend · 12 firmware · 7 dashboard'], {x: x2 + 0.25, y: 4.2, w: w2 - 0.5, h: 2.2, fontSize: 14});
  s.addNotes('Một trạm thật gửi 0,1 msg/s nên 50 msg/s tương đương khoảng 500 trạm.');
}

// =============================================================== 17. Kết luận
{
  const s = slide('Kết luận', 'Kết luận');
  const rows = [[th('KPI'), th('Kết quả'), th('')],
    ['Dự báo vượt persistence', '12/12 cặp biến × tầm', '✔'], ['MAE T 1h · H 1h · F1 mưa 3h', '0,30 °C · 1,86 % · 0,839', '✔'],
    ['Cảnh báo 4 cấp tại edge, chạy offline', 'rule + RF 17 kB, khớp C/Python', '✔'], ['Recall cấp ≥ 2 theo sự kiện', '1,00 (mô phỏng)', '◐'],
    ['≥ 50 thiết bị, mất gói ≈ 0', '0 %', '✔'], ['ML tự viết, Docker, README', 'mlcore + 76 test', '✔'],
    ['72 h ổn định, độ trễ end-to-end thật', 'cần phần cứng', '⚙']];
  s.addTable(rows, tableOpts(M, 1.4, 7.4, [3.6, 3.1, 0.7], 0.6));
  const x2 = M + 7.8, w2 = W - M - x2;
  card(s, x2, 1.4, w2, 5.1);
  text(s, 'Hướng phát triển', {x: x2 + 0.3, y: 1.55, w: w2 - 0.6, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: C.deep});
  bullets(s, ['Thu dữ liệu khí thật, huấn luyện lại, cập nhật qua OTA', 'MQ-135/MQ-5 giảm nhạy chéo cồn; cảm biến PM2.5',
    'LoRa/NB-IoT, pin mặt trời, nhiều trạm (mesh)', 'Federated learning, lượng tử hoá int8', 'OTA mô hình qua MQTT'],
  {x: x2 + 0.3, y: 2.1, w: w2 - 0.6, h: 4.3, fontSize: 15});
  s.addNotes('Nhấn mạnh: hệ thống là nguyên mẫu học thuật, không thay thế thiết bị báo gas đã chứng nhận.');
}

// =============================================================== 18. Demo
{
  const s = slide(null, 'Kết luận', 'DARK');
  s.addText('Demo và hỏi đáp', {placeholder: 'title'});
  s.addText([
    {text: 'Dashboard → xả gas gần MQ-2 → LED/còi đổi cấp → Telegram → ack → rút Wi-Fi: edge vẫn cảnh báo', options: {breakLine: true}},
    {text: 'Không có phần cứng: python tools/simulator.py --events "5:lpg_mid"', options: {color: C.amber, breakLine: true}},
    {text: 'github.com/danhle396/pythonnhung', options: {fontSize: 14}},
  ], {placeholder: 'body'});
  [0, 1, 2, 3].forEach(i => dot(s, M + i * 0.55, 1.4, 0.38, LV[i]));
  s.addNotes('Kịch bản chi tiết: docs/report/kich_ban_demo.md.');
}

// ghi file, bỏ các mục "thư mục" trong ZIP (một số dịch vụ cloud không mở được file có các mục này)
(async () => {
  const JSZip = require('jszip');
  const src = await JSZip.loadAsync(await pres.write({outputType: 'nodebuffer'}));
  const dst = new JSZip();
  for (const [name, f] of Object.entries(src.files)) if (!f.dir) dst.file(name, await f.async('nodebuffer'), {createFolders: false});
  require('fs').writeFileSync(OUT, await dst.generateAsync({type: 'nodebuffer', compression: 'DEFLATE'}));
  console.log('Đã ghi', OUT);
})();
