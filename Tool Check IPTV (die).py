import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# ====== CẤU HÌNH ======
TIMEOUT = 8          # Thời gian chờ tối đa cho mỗi link (giây)
THREADS = 10         # Số máy ảo -> 10 luồng chạy song song
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
}
# =====================

def fetch_playlist(url):
    """Tải nội dung playlist từ URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"⚠️ Lỗi khi tải playlist: {e}")
        sys.exit(1)

def parse_playlist(content):
    """Phân tích M3U, trả về danh sách (extinf_line, url)."""
    lines = content.splitlines()
    channels = []
    current_extinf = None
    for line in lines:
        line = line.strip()
        if line.startswith('#EXTINF:'):
            current_extinf = line
        elif line and not line.startswith('#') and current_extinf:
            if line.startswith(('http://', 'https://')):
                channels.append((current_extinf, line))
            else:
                print(f"⚠️ Bỏ qua link không hợp lệ: {line}")
            current_extinf = None
    return channels

def extract_channel_name(extinf_line):
    """Trích xuất tên kênh từ dòng #EXTINF."""
    match = re.search(r',([^,]+)$', extinf_line)
    return match.group(1).strip() if match else "Không rõ tên"

def is_stream_alive(stream_url):
    """Kiểm tra link có hoạt động không."""
    try:
        resp = requests.head(stream_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            return True
        resp = requests.get(stream_url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        if resp.status_code == 200:
            try:
                next(resp.iter_content(1))
                return True
            except:
                return False
        return False
    except Exception:
        return False

def check_channel(channel):
    """Kiểm tra một kênh, trả về (extinf_line, url, alive)."""
    extinf_line, url = channel
    alive = is_stream_alive(url)
    return (extinf_line, url, alive)

def main():
    playlist_url = input("🔗 Dán link danh sách M3U (hoặc đường dẫn file) vào đây: ").strip()
    if not playlist_url:
        print("❌ Bạn chưa nhập link nào!")
        return
    
    print("📡 Đang tải playlist...")
    content = fetch_playlist(playlist_url)
    
    print("📝 Đang phân tích danh sách kênh...")
    channels = parse_playlist(content)
    total = len(channels)
    if total == 0:
        print("❌ Không tìm thấy kênh nào trong playlist!")
        return
    print(f"✅ Tìm thấy {total} kênh.\n")
    
    print(f"🚀 Bắt đầu kiểm tra với {THREADS} máy ảo, mỗi lần {THREADS} kênh...")
    
    dead_channels = []   # chỉ lưu kênh chết
    checked = 0
    
    for i in range(0, total, THREADS):
        batch = channels[i:i+THREADS]
        print(f"\n🔍 Lô {i//THREADS + 1}: kiểm tra {len(batch)} kênh...")
        
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            future_to_channel = {executor.submit(check_channel, ch): ch for ch in batch}
            for future in as_completed(future_to_channel):
                extinf_line, url, alive = future.result()
                checked += 1
                name = extract_channel_name(extinf_line)
                if alive:
                    print(f"   ✅ SỐNG: {name}")
                else:
                    print(f"   ❌ CHẾT: {name}")
                    dead_channels.append((extinf_line, url))
                print(f"      Tiến độ: {checked}/{total}")
    
    # Ghi file chỉ chứa các kênh chết (định dạng M3U)
    if dead_channels:
        with open("dead.txt", "w", encoding="utf-8") as f:
            for extinf_line, url in dead_channels:
                f.write(f"{extinf_line}\n{url}\n\n")
        print(f"\n💀 Hoàn tất! Đã lưu {len(dead_channels)} kênh CHẾT vào file 'dead.txt'")
        print("   Bạn có thể dùng file này để kiểm tra hoặc thay thế link hỏng.")
    else:
        print("\n🎉 Tuyệt vời! Không có kênh chết nào. Toàn bộ playlist hoạt động tốt.")

if __name__ == "__main__":
    main()