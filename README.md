# Logwork tổng hợp 2 Jira (enotion + vortech)

Dashboard dạng lưới (giống ảnh) hiển thị **số giờ logwork / thành viên / ngày**,
gom theo team (GD, STATIC, ANIM, FE, QC, …), cộng dồn **cả 2 Jira**:

- **enotion** (`~/.jira-connect/config.json`) → đọc **TẤT CẢ** board.
- **vortech** (`~/.jira-connect/vortechinc.json`) → đọc board **APK** (APEK).
  (Đổi project bằng biến `VORTECH_PROJECT`, ví dụ `VORTECH_PROJECT= logwork.py` = mọi board.)

Cùng một người có **accountId khác nhau** ở mỗi Jira, nhưng **display name / số ID đầu**
giống nhau → dữ liệu được gộp theo ID đầu đó (fallback theo tên).

## Chạy web (live)
```bash
./start.sh            # mặc định port 8765
# mở http://127.0.0.1:8765/  — đổi khoảng ngày ở ô Từ/Đến, bấm Cập nhật.
```
Lệnh đầy đủ:
```bash
~/chatbot-discord/.venv/bin/python logwork.py --port 8765
```

## Xuất file HTML tĩnh (mở không cần server)
```bash
~/chatbot-discord/.venv/bin/python logwork.py --static report.html \
    --from 2026-10-19 --to 2026-10-30
```
Bỏ `--from/--to` → dùng 2 tuần đầy đủ gần nhất.

## Làm mới danh sách thành viên (từ Google Sheet Resource)
```bash
~/chatbot-discord/.venv/bin/python logwork.py --refresh-members
```

## Host public (GitHub + Vercel)
Trang Vercel là **bản static**: frontend tự đọc `data.json` (đã commit sẵn).
`data.json` được làm mới **tự động** bởi GitHub Actions
(`.github/workflows/refresh-data.yml`, chạy mỗi 30 phút + chạy tay từ tab Actions)
→ commit về repo → Vercel tự deploy lại.

Cần 1 lần setup trong **GitHub repo → Settings → Secrets and variables → Actions**:
- `JIRA_ENOTION_URL` / `JIRA_ENOTION_EMAIL` / `JIRA_ENOTION_TOKEN`
- `JIRA_VORTECH_URL` / `JIRA_VORTECH_EMAIL` / `JIRA_VORTECH_TOKEN`

Vercel: **Import repo** (không cần environment variable nào — code chỉ chạy CI).
Lưu ý: repo phải **public** (Actions cron + Vercel free cần repo public).

Local vẫn chạy song song: khi mở qua `http://127.0.0.1:8765/` thì trang dùng API
live (chọn ngày được); khi mở qua host Vercel thì dùng `data.json` (chế độ tĩnh).

Lệnh sinh `data.json` thủ công (cùng code CI chạy):
```bash
~/chatbot-discord/.venv/bin/python logwork.py --json
```

## Cấu trúc
- `logwork.py` — fetch 2 Jira + server + xuất snapshot (stdlib, urllib).
- `logwork.html` — giao diện (fetch `/api/logwork`, hoặc dùng dữ liệu nhúng khi mở file tĩnh).
- `members.json` — roster studio (id / jira_id / team), tạo bởi `--refresh-members`.

Ghi chú: lần fetch đầu cho một khoảng ngày mất ~15 giây (quét toàn bộ worklog);
các lần sau được cache ở server.
