# pywebcopy/compat.py
# Drop-in replacement for cgi.parse_header on Python 3.13+
try:
    # Python <=3.11 (3.12 still had cgi but deprecated)
    from cgi import parse_header  # type: ignore[attr-defined]
except Exception:
    from email.message import Message

    def parse_header(line: str):
        """
        Return (value, params_dict) like cgi.parse_header.
        Works for common 'Content-Type' and 'Content-Disposition' style headers.
        """
        # If the caller passed just the value without a header name, assume Content-Type
        if ":" in line:
            header_name, header_value = line.split(":", 1)
            header_name = header_name.strip()
            header_value = header_value.strip()
        else:
            header_name = "Content-Type"
            header_value = line.strip()

        msg = Message()
        msg[header_name] = header_value

        # Value (left of ';'), lowercased to match cgi.parse_header behavior in practice
        raw = msg.get(header_name)
        value = (raw.split(";", 1)[0] if raw else "").strip().lower()

        # Params as dict; first item of get_params() is the main value, skip it
        try:
            params = dict(msg.get_params(header=header_name)[1:])
        except Exception:
            params = {}

        return value, params
