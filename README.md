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

## Host public — Cloudflare Pages (thay Vercel)
Trang là **bản static đọc `data.json`** trong repo. `data.json` được máy bạn tự làm mới
(LaunchAgent `com.pma-lily.logwork-refresh`, 15 phút/lần: `logwork.py --json` → `git push`)
→ **Cloudflare Pages tự deploy lại** mỗi lần push.

### Setup 1 lần trên Cloudflare (miễn phí):
1. Vào https://dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Chọn repo `logwork-web` → **Begin setup**.
3. Cấu hình build:
   - **Framework preset**: *None*
   - **Build command**: *(bỏ trống)*
   - **Build output directory**: `/`
4. **Save and Deploy**. Xong — mỗi lần push `data.json` là Cloudflare tự cập nhật (domain kiểu `logwork-web.pages.dev`).

File `_redirects` trong repo đã map `/` → `logwork.html`, nên mở gốc domain là thấy grid.
Không cần bot, không cần cron Actions, không cần repo public (vì dùng job local).

Local vẫn chạy song song: http://127.0.0.1:8765/ (API live).

## Cấu trúc
- `logwork.py` — fetch 2 Jira + server + xuất snapshot (stdlib, urllib).
- `logwork.html` — giao diện (fetch `/api/logwork`, hoặc dùng dữ liệu nhúng khi mở file tĩnh).
- `members.json` — roster studio (id / jira_id / team), tạo bởi `--refresh-members`.

Ghi chú: lần fetch đầu cho một khoảng ngày mất ~15 giây (quét toàn bộ worklog);
các lần sau được cache ở server.
