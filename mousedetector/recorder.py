import re

def sanitize_label(label):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", label.strip()).strip("-")
    return s or "unlabeled"

def filename_for(label, start_dt):
    return f"{start_dt:%Y-%m-%d}_{sanitize_label(label)}_{start_dt:%H%M}.wav"

def sidecar_for(label, start_dt, duration_s, device, sample_rate, channels, fmt, host):
    return {
        "label": sanitize_label(label),
        "date": f"{start_dt:%Y-%m-%d}",
        "start_iso": start_dt.isoformat(timespec="seconds"),
        "duration_s": int(duration_s),
        "device": device,
        "sample_rate": int(sample_rate),
        "channels": int(channels),
        "format": fmt,
        "host": host,
    }

def arecord_cmd(device, sample_rate, channels, fmt, duration_s, out_path):
    return ["arecord", "-D", device, "-f", fmt, "-r", str(int(sample_rate)),
            "-c", str(int(channels)), "-d", str(int(duration_s)), out_path]
