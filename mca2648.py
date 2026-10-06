import random
import socket

# ----------------------------------------------------------------------------
# 1. CORE CRC LOGIC (no UI code here, so it can be tested on its own)
# ----------------------------------------------------------------------------

PRESETS = {
    "CRC-4 (ITU)": "10011",
    "CRC-8": "100000111",
    "CRC-16 (CCITT)": "10001000000100001",
    "Custom": "",
}


def is_all_zeros(text):
    """True if every character is 0."""
    for character in text:
        if character != "0":
            return False
    return True


def remove_spaces(text):
    """Remove spaces, tabs, line breaks and non-breaking spaces (copy and paste often brings them)."""
    result = ""
    for character in text:
        if character not in " \t\r\n\u00a0":
            result = result + character
    return result


def text_to_bits(text):
    """Convert text to bits: every character becomes 8-bit groups (UTF-8, so any language works)."""
    if text == "":
        raise ValueError("Enter some text to send.")
    raw = text.encode("utf-8")
    if len(raw) > 16:
        raise ValueError("Keep the text to 16 bytes or fewer (about 16 English letters).")
    bits = ""
    for number in raw:
        bits = bits + format(number, "08b")
    return bits


def bits_to_text(bits):
    """Turn 8-bit groups back into text. Bytes that are damaged show as the character \ufffd."""
    raw = bytearray()
    position = 0
    while position + 8 <= len(bits):
        group = bits[position:position + 8]
        raw.append(int(group, 2))
        position = position + 8
    text = raw.decode("utf-8", errors="replace")
    result = ""
    for character in text:
        number = ord(character)
        if number < 32 or (number >= 127 and number < 160):
            result = result + "\ufffd"          # a control character: this byte was damaged
        else:
            result = result + character
    return result


def validate_dataword(bits):
    bits = remove_spaces(bits)
    if bits == "":
        raise ValueError("Enter the dataword bits to send.")
    for character in bits:
        if character != "0" and character != "1":
            raise ValueError("A dataword can contain only 0s and 1s. To send letters, switch to Text.")
    if len(bits) > 128:
        raise ValueError("Keep the dataword to 128 bits or fewer.")
    return bits


def validate_divisor(divisor):
    divisor = remove_spaces(divisor)          # spaces are allowed, like in the Dataword box
    problem = False
    for character in divisor:
        if character != "0" and character != "1":
            problem = True
    if len(divisor) < 2 or len(divisor) > 33:
        problem = True
    if problem == False and divisor[0] != "1":
        problem = True
    if problem:
        raise ValueError("The divisor must be 2-33 bits, start with 1, and use only 0s and 1s.")
    return divisor


def poly_to_str(bits):
    """'10011' -> 'x^4 + x + 1'  (leading zeros are ignored; all zeros -> '0')"""
    n = len(bits)
    terms = []
    for i in range(n):
        if bits[i] == "1":
            power = n - 1 - i
            if power == 0:
                terms.append("1")
            elif power == 1:
                terms.append("x")
            else:
                terms.append("x^" + str(power))
    if len(terms) == 0:
        return "0"
    return " + ".join(terms)


def flip_bit_in(bits, position):
    """Return the bits with one bit changed (0 becomes 1, 1 becomes 0)."""
    if bits[position] == "1":
        new_bit = "0"
    else:
        new_bit = "1"
    return bits[:position] + new_bit + bits[position + 1:]


def count_differences(first, second):
    """How many positions are different between two bit strings."""
    count = 0
    for i in range(len(first)):
        if first[i] != second[i]:
            count = count + 1
    return count


def xor_divide(bits, divisor):
    """
    Modulo-2 (XOR) division.
    Returns (steps, remainder); steps is a list of (offset, working_string_after_xor).
    The quotient is not kept: CRC discards it.
    """
    work = list(bits)
    size = len(divisor)
    steps = []
    for i in range(len(work) - size + 1):
        if work[i] == "1":                   # leading 1 -> XOR the divisor in
            for j in range(size):
                if work[i + j] == divisor[j]:
                    work[i + j] = "0"
                else:
                    work[i + j] = "1"
            steps.append((i, "".join(work)))
    remainder = "".join(work[len(work) - (size - 1):])
    return steps, remainder


def make_codeword(dataword, divisor):
    """Sender (encoder): returns (augmented_dataword, steps, remainder, codeword)."""
    augmented = dataword + "0" * (len(divisor) - 1)       # add n - k zeros on the right
    steps, remainder = xor_divide(augmented, divisor)
    codeword = dataword + remainder                       # append the remainder to the dataword
    return augmented, steps, remainder, codeword


def check_codeword(received, divisor):
    """Receiver (decoder): returns (steps, syndrome, ok). ok is True when the syndrome is all zeros."""
    steps, syndrome = xor_divide(received, divisor)
    ok = is_all_zeros(syndrome)
    return steps, syndrome, ok


def format_steps(bits, divisor, steps):
    """Turn the division into aligned text lines: every step, then the remainder."""
    r = len(divisor) - 1
    lines = [bits]
    for step in steps:
        offset = step[0]
        after = step[1]
        lines.append(" " * offset + divisor)
        lines.append(after)
    if len(steps) > 0:
        last = steps[-1][1]
    else:
        last = bits
    lines.append("")
    lines.append("Remainder = " + last[-r:])
    return "\n".join(lines)


def make_table(rows):
    """Turn (label, value) pairs into aligned lines such as 'Remainder   : 1110'."""
    width = 0
    for row in rows:
        if len(row[0]) > width:
            width = len(row[0])
    lines = []
    for row in rows:
        lines.append(row[0].ljust(width) + " : " + row[1])
    return "\n".join(lines)



# ----------------------------------------------------------------------------
# 2. USER INTERFACE (NiceGUI)
# ----------------------------------------------------------------------------
CSS = """
:root{--bg:#eef1f4;--panel:#fff;--ink:#16202b;--mute:#5d6b7a;--line:#d3dae1;--data:#dfe7ef;--crc:#ffd27a;--crcink:#3d2a00;--bad:#d6402f;--good:#1f8a5b;--acc:#1d5fa8}
body{color:var(--ink);font-family:'Bricolage Grotesque',system-ui,sans-serif;
 background:radial-gradient(900px 380px at 85% -8%,color-mix(in srgb,var(--acc) 20%,transparent),transparent),
 radial-gradient(700px 300px at 0% 30%,color-mix(in srgb,var(--crc) 16%,transparent),transparent),var(--bg)}
.main{max-width:880px;width:100%;margin:0 auto;padding:16px 16px 48px;gap:14px}
.title{font-size:clamp(30px,6vw,44px);font-weight:700;line-height:1.1;background:linear-gradient(90deg,var(--acc),var(--good));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub,.hint{color:var(--mute)}.hint{font-size:14px}
.sec{width:100%;background:var(--panel);border:1px solid var(--line);border-left:6px solid var(--acc);border-radius:16px;padding:18px;box-shadow:0 6px 24px -14px rgba(10,30,60,.35);gap:8px}
.sec.ch{border-left-color:var(--crc)}.sec.rx{border-left-color:var(--good)}
.h2{font-size:20px;font-weight:700}
.nb{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--acc);color:#fff;font-size:14px;margin-right:10px}
.ch .nb{background:var(--crc);color:var(--crcink)}.rx .nb{background:var(--good)}
.mono{font-family:'JetBrains Mono',ui-monospace,Menlo,monospace}
.pre{white-space:pre;overflow:auto;max-height:340px;max-width:100%;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;font-size:13px;line-height:1.35}
.err{color:var(--bad);font-size:14px;min-height:20px}
.steps{position:sticky;top:0;z-index:5;width:100%;gap:8px;padding:10px 0}
.pill{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:8px 10px;border:1px solid var(--line);border-radius:999px;font-size:14px;font-weight:700;color:var(--mute);background:var(--panel);transition:all .3s}
.pill .pn{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--data);font-size:12px}
.pill.on{color:var(--ink);border-color:var(--acc)}.pill.on .pn{background:var(--acc);color:#fff}
.pill.done{color:var(--ink)}.pill.done .pn{background:var(--good);color:#fff}
.bits{display:flex;flex-wrap:wrap;gap:3px;margin:8px 0}
.bit{width:30px;height:38px;display:grid;place-items:center;border-radius:5px;border:1px solid var(--line);background:var(--data);font-family:'JetBrains Mono',monospace;font-size:15px;transition:transform .1s}
.bit.c{background:var(--crc);color:var(--crcink);border-color:transparent}
.bit.x{background:var(--bad);color:#fff;border-color:transparent;font-weight:700}
.bit.clk{cursor:pointer}.bit.clk:hover{transform:translateY(-3px);border-color:var(--bad)}
.bit.pop{animation:pop .35s both;animation-delay:calc(var(--n,0)*12ms)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--mute)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;background:var(--data);border:1px solid var(--line)}
.legend i.c{background:var(--crc)}.legend i.x{background:var(--bad)}
.wire{display:flex;align-items:center;gap:10px;margin:14px 0 4px;width:100%}
.node{flex:0 0 auto;padding:8px 12px;border:2px solid var(--line);border-radius:8px;font-weight:700;font-size:14px;background:var(--bg);transition:all .3s}
.node.txon{border-color:var(--acc);box-shadow:0 0 0 4px color-mix(in srgb,var(--acc) 25%,transparent)}
.node.rxon{border-color:var(--good);box-shadow:0 0 0 4px color-mix(in srgb,var(--good) 25%,transparent)}
.lane{position:relative;flex:1;min-width:0;height:48px;border-top:2px dashed var(--line);border-bottom:2px dashed var(--line);overflow:hidden}
.pkt{position:absolute;top:50%;left:0;width:min(150px,60%);height:28px;margin-top:-14px;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:1px;overflow:hidden;padding:3px;background:var(--panel);border:2px solid var(--acc);border-radius:6px;box-shadow:0 4px 14px -4px var(--acc);animation:fly 2.2s cubic-bezier(.45,0,.3,1) forwards}
.pkt.dense{gap:0}
.pkt i{min-width:0;background:var(--data)}.pkt i.c{background:var(--crc)}.pkt i.x{background:var(--bad)}
.verdict{width:100%;font-size:20px;font-weight:700;padding:16px 18px;border-radius:12px;border:2px solid;background:color-mix(in srgb,currentColor 9%,var(--panel))}
.verdict span{display:block;font-size:15px;font-weight:400;color:var(--ink);margin-top:6px}
.verdict.ok{color:var(--good);animation:glow .9s}.verdict.bad{color:var(--bad);animation:shake .45s}.verdict.warn{color:var(--crc);animation:glow .9s}
.verdict.sm{font-size:14px;font-weight:400;margin-top:8px;padding:12px 14px;color:var(--ink);border-color:var(--crc);animation:none}
.sec{scroll-margin-top:76px}
body{cursor:default;-webkit-user-select:none;user-select:none}
input,textarea{cursor:text;-webkit-user-select:text;user-select:text}
.pre,.table-text{-webkit-user-select:text;user-select:text}
@keyframes fly{from{left:0}to{left:calc(100% - min(150px,60%))}}
@keyframes pop{from{transform:scale(.3);opacity:0}to{transform:none;opacity:1}}
@keyframes shake{20%{transform:translateX(-9px)}40%{transform:translateX(9px)}60%{transform:translateX(-5px)}80%{transform:translateX(5px)}}
@keyframes glow{from{box-shadow:0 0 0 0 color-mix(in srgb,currentColor 55%,transparent)}to{box-shadow:0 0 0 20px transparent}}
@media (max-width:560px){.pill{font-size:0;gap:0}.pill .pn{font-size:12px}.bit{width:24px;height:32px;font-size:13px}}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01ms!important;transition:none!important}}
"""


# Text of the "How does CRC work?" panel. It follows the lecture slides (Error Detection & Correction).
HOW_IT_WORKS = """
A **Cyclic Redundancy Check** (CRC) is an error-detecting code used in computer networks and storage devices to spot accidental changes or corruption in digital data during transmission.

**Step by step**\n
**Sender:**\n
• It has k datawords; n codewords;\n
• The size of the dataword is augmented by adding n – k 0’s to the RHS of the word.\n
• The n bit result is fed in to the generator.\n
• The generator uses a divisor of size n – k + 1, predefined and agreed upon.\n
• It divides the dataword by the divisor(Modulo 2). \n
• The quotient of the division is discarded.\n
• The remainder is appended to the dataword to create the codeword.\n

**Receiver**\n
• It receives the codeword.\n
• A copy of all n bits is fed to the checker, which is a replica of the generator.\n
• The remainder produced by the checker is a syndrome of n – k bits, which is fed to the decision logic analyzer.\n
• It has a simple function; If the syndrome bits are all 0’s, the 4 leftmost bits of the codeword are accepted as the dataword (interpreted as no error).\n
• Otherwise, the 4 bits are discarded (error).\n


**Small example** (data `1101`, generator `1011`):
```
{steps}
```

"""


def build_page():
    from nicegui import ui

    ui.add_head_html('<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700&'
                     'family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">')
    ui.add_css(CSS)
    ui.colors(primary="#1d5fa8", positive="#1f8a5b", negative="#d6402f")

    # The "notebook": everything the page needs to remember.
    #   s["S"] holds the current dataword, divisor, remainder and codeword; "k" is the dataword length.
    #   s["recv"] is the copy of the codeword that is sent (the user may damage it).
    s = {"mode": "bin", "S": None, "recv": "", "busy": False, "step": (1, 0), "verdict": None,
         "anim_tx": False, "anim_got": False, "flying": False, "rx_on": False}

    # ---------- pieces of the screen (re-drawn when their state changes) ----------
    def make_click(click, position):
        def handler():
            click(position)
        return handler

    def bits_row(bits, k, ref=None, click=None, animate=False):
        # bits at positions 0 .. k-1 are the dataword, the rest are the CRC (remainder) bits
        with ui.element("div").classes("bits"):
            for i in range(len(bits)):
                b = bits[i]
                cls = "bit"
                if ref is not None and ref[i] != b:
                    cls = cls + " x"
                elif i >= k:
                    cls = cls + " c"
                if animate:
                    cls = cls + " pop"
                if click:
                    cls = cls + " clk"
                el = ui.label(b).classes(cls).style("--n:" + str(min(i, 60)))
                if click:
                    el.on("click", make_click(click, i))

    @ui.refreshable
    def stepper():
        a = s["step"][0]
        d = s["step"][1]
        names = ["Sender", "Channel", "Receiver"]
        with ui.row().classes("steps"):
            for i in range(1, 4):
                kind = ""
                symbol = str(i)
                if i <= d:
                    kind = "done"
                    symbol = "✓"
                elif i == a:
                    kind = "on"
                with ui.element("div").classes("pill " + kind):
                    ui.label(symbol).classes("pn")
                    ui.label(names[i - 1])

    @ui.refreshable
    def tx_bits():
        if s["S"] is not None:
            bits_row(s["S"]["codeword"], s["S"]["k"], animate=s["anim_tx"])

    @ui.refreshable
    def rx_bits():
        if s["S"] is not None:
            bits_row(s["recv"], s["S"]["k"], s["S"]["codeword"], click=on_bit)

    @ui.refreshable
    def got_bits():
        if s["S"] is not None:
            bits_row(s["recv"], s["S"]["k"], animate=s["anim_got"])   # no red marks: a real receiver cannot see which bits changed

    @ui.refreshable
    def wire():
        sender_class = "node"
        if s["flying"]:
            sender_class = "node txon"
        receiver_class = "node"
        if s["rx_on"]:
            receiver_class = "node rxon"
        with ui.element("div").classes("wire"):
            ui.label("Sender").classes(sender_class)
            with ui.element("div").classes("lane"):
                if s["flying"]:
                    packet_class = "pkt"
                    if len(s["recv"]) > 40:
                        packet_class = "pkt dense"      # long codeword: no gaps, so every bit still gets some width
                    with ui.element("div").classes(packet_class):
                        for i in range(len(s["recv"])):
                            kind = ""
                            if s["recv"][i] != s["S"]["codeword"][i]:
                                kind = "x"
                            elif i >= s["S"]["k"]:
                                kind = "c"
                            ui.element("i").classes(kind)
            ui.label("Receiver").classes(receiver_class)

    @ui.refreshable
    def verdict_box():
        v = s["verdict"]
        if v is not None:
            with ui.element("div").classes("verdict " + v["cls"]).props('role=status'):
                ui.label(v["text"])

    def legend(items):
        with ui.element("div").classes("legend"):
            for item in items:
                kind = item[0]
                name = item[1]
                with ui.element("span"):
                    ui.element("i").classes(kind)
                    ui.label(name).classes("inline")

    def scroll_to(dom_id):
        ui.run_javascript("document.getElementById('" + dom_id + "').scrollIntoView({behavior:'smooth',block:'nearest'})")

    def set_step(a, d):
        s["step"] = (a, d)
        stepper.refresh()

    def set_busy(b):
        s["busy"] = b
        all_controls = [send_btn, generate_btn, clean_btn, one_btn, burst_btn, flip_btn, pos_in, reset_btn]
        for control in all_controls:
            if b:
                control.disable()
            else:
                control.enable()

    ex_aug, ex_steps, ex_rem, ex_codeword = make_codeword("1101", "1011")
    ex_text = format_steps(ex_aug, "1011", ex_steps)

    # ---------- page layout ----------
    with ui.column().classes("main"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("CRC Lab").classes("title")
            reset_btn = ui.button("Reset").props("outline no-caps")
        stepper()
        with ui.expansion("How does CRC work? (explained step by step)").classes("w-full") as how_exp:
            ui.markdown(HOW_IT_WORKS.format(steps=ex_text))

        # --- 1. Sender (encoder) ---
        with ui.column().classes("sec"):
            with ui.row().classes("items-center"):
                ui.label("1").classes("nb")
                ui.label("Sender (Encoder): build the codeword").classes("h2")
            with ui.row().classes("w-full items-end gap-3"):
                mode_toggle = ui.toggle({"bin": "Binary", "txt": "Text"}, value="bin").props("no-caps")
                data_in = ui.input("Dataword", value="").props('outlined dense placeholder="e.g. 1101011011"').classes("mono grow")
            with ui.row().classes("w-full items-end gap-3"):
                preset = ui.select(list(PRESETS), value="Custom", label="Preset divisor (generator)").props("outlined dense").classes("grow")
            with ui.row().classes("w-full items-end gap-3"):
                divisor_in = ui.input("Divisor bits", value="").props('outlined dense placeholder="e.g. 10011 (must start with 1)"').classes("mono grow")
                generate_btn = ui.button("Generate codeword").props("no-caps unelevated")
            err = ui.label("").classes("err").props('role=alert')
            tx_out = ui.column().classes("w-full").props("id=txcard")
            with tx_out:
                info = ui.label("").classes("mono whitespace-pre-wrap break-all text-sm")
                with ui.expansion("Show the division steps").classes("w-full") as tx_exp:
                    tx_div = ui.label("").classes("pre mono")
                legend((("", "dataword (k bits)"), ("c", "remainder / CRC bits (n - k bits)")))
                tx_bits()
            tx_out.set_visibility(False)

        # --- 2. Channel ---
        ch_card = ui.column().classes("sec ch").props("id=chcard")
        with ch_card:
            with ui.row().classes("items-center"):
                ui.label("2").classes("nb")
                ui.label("Channel: send the codeword").classes("h2")
            ui.label("Leave the codeword alone for a clean transmission, or corrupt it: click any bit to flip it, "
                     "or use the buttons. Then press Send.").classes("hint")
            with ui.row().classes("gap-2"):
                clean_btn = ui.button("Clean transmission").props("outline no-caps")
                one_btn = ui.button("Flip 1 random bit").props("outline no-caps")
                burst_btn = ui.button("Burst error (4 bits)").props("outline no-caps")
            with ui.row().classes("items-center gap-2"):
                pos_in = ui.number("Flip bit number", min=1, precision=0).props("outlined dense").classes("w-40")
                flip_btn = ui.button("Flip it").props("outline no-caps")
                ui.label("Counts from 1 at the left of the codeword.").classes("hint")
            legend((("", "dataword"), ("c", "CRC bits"), ("x", "flipped in transit")))
            rx_bits()
            flip_info = ui.label("").classes("hint")
            send_btn = ui.button("Send ▶").props("no-caps unelevated size=lg")
            wire()
        ch_card.set_visibility(False)

        # --- 3. Receiver (decoder) ---
        rx_card = ui.column().classes("sec rx").props("id=rxcard")
        with rx_card:
            with ui.row().classes("items-center"):
                ui.label("3").classes("nb")
                ui.label("Receiver (Decoder): check the codeword").classes("h2")
            got_bits()
            chk = ui.label("").classes("hint")
            recv_info = ui.label("").classes("mono whitespace-pre-wrap break-all text-sm")
            verdict_box()
            with ui.expansion("Show the division steps").classes("w-full") as rx_exp:
                rx_div = ui.label("").classes("pre mono")
        rx_card.set_visibility(False)

    # ---------- behaviour ----------
    def on_mode(e):
        s["mode"] = e.value                       # the typed text is kept; only the hint changes
        if e.value == "bin":
            data_in.props('placeholder="e.g. 1101011011"')
        else:
            data_in.props('placeholder="e.g. Hello (up to 16 bytes)"')

    def divisor_bits():
        text = divisor_in.value
        if text is None:
            text = ""
        return validate_divisor(text)

    def dataword_bits():
        raw = data_in.value
        if raw is None:
            raw = ""
        if s["mode"] == "bin":
            return validate_dataword(raw)
        return text_to_bits(raw)

    def on_preset(e):
        if e.value in PRESETS:
            bits = PRESETS[e.value]
            if bits != "":
                divisor_in.value = bits

    def on_divisor(e):
        # keep the preset dropdown in step with what is typed
        try:
            bits = divisor_bits()
        except ValueError:
            bits = None
        name = "Custom"
        if bits is not None:
            for preset_name in PRESETS:
                if PRESETS[preset_name] == bits:
                    name = preset_name
        if preset.value != name:
            preset.value = name

    def generate():
        if s["busy"]:
            return False            # ignore Enter while a codeword is travelling
        err.set_text("")
        try:
            dataword = dataword_bits()
            divisor = divisor_bits()
        except ValueError as ex:
            err.set_text(str(ex))
            return False
        augmented, steps, remainder, codeword = make_codeword(dataword, divisor)
        k = len(dataword)
        n = len(codeword)
        r = len(divisor) - 1
        s["S"] = {"dataword": dataword, "divisor": divisor, "remainder": remainder,
                  "codeword": codeword, "k": k, "mode": s["mode"]}
        s["recv"] = codeword

        rows = []
        if s["mode"] == "txt":
            rows.append(("Message", data_in.value))
        rows.append(("Dataword (k = " + str(k) + " bits)", dataword))
        rows.append(("Dataword polynomial", poly_to_str(dataword)))
        rows.append(("Divisor (n - k + 1 = " + str(r + 1) + " bits)", divisor))
        rows.append(("Divisor polynomial", poly_to_str(divisor)))
        rows.append(("Augmented dataword", augmented + "  (+" + str(r) + " zeros)"))
        rows.append(("Remainder", remainder))
        rows.append(("Codeword (n = " + str(n) + " bits)", codeword))
        info.set_text(make_table(rows))

        tx_div.set_text(format_steps(augmented, divisor, steps))
        s["anim_tx"] = True
        tx_bits.refresh()
        tx_out.set_visibility(True)
        ch_card.set_visibility(True)
        draw_channel()
        scroll_to("txcard")         # stay with the codeword that was just built (do not jump to the channel)
        return True

    def draw_channel():
        n = count_differences(s["recv"], s["S"]["codeword"])
        if n == 0:
            flip_info.set_text("Codeword is unchanged: a clean transmission.")
        elif n == 1:
            flip_info.set_text("1 bit flipped (a single bit error). Click a red bit to restore it.")
        else:
            flip_info.set_text(str(n) + " bits flipped (a burst error). Click a red bit to restore it.")
        rx_bits.refresh()
        rx_card.set_visibility(False)
        s["rx_on"] = False
        s["flying"] = False
        s["verdict"] = None
        wire.refresh()
        verdict_box.refresh()
        set_step(2, 1)

    def flip(i):
        s["recv"] = flip_bit_in(s["recv"], i)

    def on_bit(i):
        if s["busy"] == False and s["S"] is not None:
            flip(i)
            draw_channel()

    def clean():
        s["recv"] = s["S"]["codeword"]
        draw_channel()

    def random_flip():
        position = random.randrange(len(s["recv"]))
        flip(position)
        draw_channel()

    def flip_at():
        n = len(s["recv"])
        number = pos_in.value
        if number is None or number < 1 or number > n:
            ui.notify("Enter a bit number from 1 to " + str(n) + ".", type="warning")
            return
        flip(int(number) - 1)
        draw_channel()

    def burst():
        total = len(s["recv"])
        length = 4
        if total < 4:
            length = total          # very short codeword: flip every bit it has
        start = random.randrange(total - length + 1)
        for i in range(start, start + length):
            flip(i)
        draw_channel()

    def send():
        if s["busy"] or s["S"] is None:
            return
        set_busy(True)
        rx_card.set_visibility(False)
        s["flying"] = True
        s["rx_on"] = False
        wire.refresh()                  # the CSS animation starts when the packet appears
        ui.timer(2.3, arrive, once=True)

    def arrive():
        s["flying"] = False
        s["rx_on"] = True
        wire.refresh()
        s["anim_got"] = True
        got_bits.refresh()
        s["verdict"] = None
        verdict_box.refresh()
        recv_info.set_text("")
        chk.set_text("Codeword received. Checking…")
        rx_card.set_visibility(True)
        set_step(3, 2)
        scroll_to("rxcard")
        ui.timer(1.0, finish, once=True)

    def finish():
        chk.set_text("")
        try:
            verify()
        finally:
            set_busy(False)         # always unlock the buttons, even if something went wrong

    def verify():
        divisor = s["S"]["divisor"]
        steps, syndrome, ok = check_codeword(s["recv"], divisor)
        if ok:
            cls = "ok"
            text = "✓ The remainder is 0, hence no error is detected."
        else:
            cls = "bad"
            text = "✗ The remainder is not 0, hence the data is corrupted."

        k = s["S"]["k"]
        got_data = s["recv"][:k]
        got_crc = s["recv"][k:]
        rows = []
        if s["S"]["mode"] == "txt":
            rows.append(("Received message", bits_to_text(got_data)))
        rows.append(("Received codeword", s["recv"]))
        rows.append(("Received dataword (k bits)", got_data))
        rows.append(("Received CRC bits", got_crc))
        rows.append(("Syndrome (remainder)", syndrome))
        report = make_table(rows)
        recv_info.set_text(report)

        s["verdict"] = {"cls": cls, "text": text}
        verdict_box.refresh()
        rx_div.set_text(format_steps(s["recv"], divisor, steps))
        set_step(3, 3)

    def reset():
        if s["busy"]:
            return                          # wait until the codeword has arrived
        # forget everything in the notebook
        s["S"] = None
        s["recv"] = ""
        s["verdict"] = None
        s["anim_tx"] = False
        s["anim_got"] = False
        s["flying"] = False
        s["rx_on"] = False
        # empty the input boxes and go back to Binary
        mode_toggle.value = "bin"
        data_in.value = ""
        divisor_in.value = ""
        preset.value = "Custom"
        pos_in.value = None
        # clear every text on the page
        err.set_text("")
        info.set_text("")
        tx_div.set_text("")
        flip_info.set_text("")
        chk.set_text("")
        recv_info.set_text("")
        rx_div.set_text("")
        # redraw the pieces that depend on the notebook (they are empty now)
        tx_bits.refresh()
        rx_bits.refresh()
        got_bits.refresh()
        wire.refresh()
        verdict_box.refresh()
        # hide the cards that only appear after a codeword exists, and close the opened panels
        tx_out.set_visibility(False)
        ch_card.set_visibility(False)
        rx_card.set_visibility(False)
        how_exp.value = False
        tx_exp.value = False
        rx_exp.value = False
        set_step(1, 0)                      # the stepper starts again at Sender
        ui.run_javascript("window.scrollTo({top: 0, behavior: 'smooth'})")

    # ---------- connect each control to its function ----------
    mode_toggle.on_value_change(on_mode)
    preset.on_value_change(on_preset)
    divisor_in.on_value_change(on_divisor)
    data_in.on("keydown.enter", generate)
    divisor_in.on("keydown.enter", generate)
    generate_btn.on_click(generate)
    clean_btn.on_click(clean)
    one_btn.on_click(random_flip)
    burst_btn.on_click(burst)
    flip_btn.on_click(flip_at)
    send_btn.on_click(send)
    reset_btn.on_click(reset)


def find_free_port(first_port):
    """Return the first port, from first_port upwards, that no other program is using."""
    port = first_port
    while port < first_port + 20:
        test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            test.bind(("0.0.0.0", port))
            test.close()
            return port
        except OSError:
            test.close()
            port = port + 1
    return first_port


def run_app():
    from nicegui import ui
    ui.page("/")(build_page)
    ui.run(title="CRC Lab - Cyclic Redundancy Check Simulator", reload=False, port=find_free_port(8080))


if __name__ in {"__main__", "__mp_main__"}:
        run_app()