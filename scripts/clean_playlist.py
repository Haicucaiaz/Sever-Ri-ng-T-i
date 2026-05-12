import sys
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# Thiết lập logging để dễ dàng theo dõi tiến trình
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ====== CẤU HÌNH KIỂM TRA ======
TIMEOUT = 8          # Thời gian chờ tối đa cho mỗi link (giây)
THREADS = 20         # Số luồng kiểm tra song song (tăng để nhanh hơn)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# ===============================

def extract_channel_name(extinf_line):
    """Trích xuất tên kênh từ dòng #EXTINF."""
    match = re.search(r',([^,]+)$', extinf_line)
    return match.group(1).strip() if match else "Không rõ tên"

def is_stream_alive(stream_url):
    """Kiểm tra một link stream có hoạt động không (trả về True/False)."""
    try:
        # Thử phương thức HEAD trước để nhanh hơn
        resp = requests.head(stream_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            return True
        # Một số server không hỗ trợ HEAD, thử GET với stream=True và chỉ đọc 1 byte
        resp = requests.get(stream_url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        if resp.status_code == 200:
            try:
                # Đọc 1 byte để chắc chắn server bắt đầu gửi dữ liệu
                next(resp.iter_content(1))
                return True
            except StopIteration:
                return False
        return False
    except Exception:
        return False

def parse_and_check(filepath):
    """Đọc file M3U, kiểm tra từng kênh, trả về danh sách các dòng còn sống."""
    alive_lines = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    channels_to_check = []
    channel_info = []  # Lưu thông tin (dòng bắt đầu, tên kênh, dòng link)
    i = 0
    logging.info("Đang phân tích cấu trúc file...")
    while i < len(lines):
        line = lines[i].strip()
        # Tìm một kênh bắt đầu bằng #EXTINF
        if line.startswith('#EXTINF'):
            # Lưu lại dòng #EXTINF và tất cả các dòng thuộc về nó (có thể có #EXTVLCOPT)
            channel_start_lines = [lines[i]]
            i += 1
            # Thu thập các dòng tiếp theo cho đến khi gặp URL
            while i < len(lines) and not lines[i].strip().startswith('#EXTINF'):
                channel_start_lines.append(lines[i])
                i += 1
            # Bây giờ, channel_start_lines[-2] hoặc tương tự là dòng URL
            # Tìm dòng URL (bắt đầu bằng http:// hoặc https://)
            url_line = None
            for l in channel_start_lines:
                if l.strip().startswith(('http://', 'https://')):
                    url_line = l
                    break
            if url_line:
                url = url_line.strip()
                name = extract_channel_name(channel_start_lines[0].strip())
                channels_to_check.append((name, url))
                channel_info.append((channel_start_lines, url_line))
        else:
            i += 1

    total = len(channels_to_check)
    logging.info(f"Tìm thấy {total} kênh. Bắt đầu kiểm tra...")

    alive_channels = []
    checked = 0
    # Kiểm tra song song
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_to_channel = {executor.submit(is_stream_alive, url): (name, url, idx) for idx, (name, url) in enumerate(channels_to_check)}
        for future in as_completed(future_to_channel):
            name, url, idx = future_to_channel[future]
            checked += 1
            if future.result():
                alive_channels.append(idx)
                logging.info(f"[{checked}/{total}] ✅ SỐNG: {name}")
            else:
                logging.info(f"[{checked}/{total}] ❌ CHẾT: {name}")

    # Tạo nội dung file mới chỉ từ các kênh sống
    new_content_lines = []
    for idx in alive_channels:
        channel_lines, url_line = channel_info[idx]
        new_content_lines.extend(channel_lines)
    return new_content_lines

def main():
    if len(sys.argv) != 2:
        logging.error("Sai cú pháp. Cần: python clean_playlist.py <path_to_playlist_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    logging.info(f"Bắt đầu làm sạch playlist: {filepath}")

    try:
        clean_lines = parse_and_check(filepath)
        if clean_lines:
            # Ghi đè lên file cũ với các dòng đã được làm sạch
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(clean_lines)
            logging.info(f"✅ Thành công! Playlist đã được cập nhật, giữ lại {len([l for l in clean_lines if l.startswith('#EXTINF')])} kênh sống.")
            logging.info(f"   Nhớ commit và push file '{filepath}' lên GitHub để áp dụng thay đổi.")
        else:
            logging.warning("⚠️ Không tìm thấy kênh nào còn sống.")
    except Exception as e:
        logging.error(f"❌ Có lỗi xảy ra: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
