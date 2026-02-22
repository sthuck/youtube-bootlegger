"""Time format conversion utilities."""


def parse_timestamp_to_seconds(timestamp: str) -> float:
    """Convert mm:ss or hh:mm:ss to float seconds.

    Args:
        timestamp: Time string in format mm:ss or hh:mm:ss.

    Returns:
        Total seconds as a float.

    Raises:
        ValueError: If the timestamp format is invalid.
    """
    parts = timestamp.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp}")

    try:
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: {timestamp}") from e


def format_seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to hh:mm:ss format for ffmpeg.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted time string in hh:mm:ss.ms format.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
