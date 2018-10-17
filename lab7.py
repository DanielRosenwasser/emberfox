import subprocess
import tkinter
import tkinter.font as tkFont
import collections
from datetime import datetime
import functools

def log_start_end_time(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        start = datetime.now()
        print('%s started at %s' % (func.__name__, start))
        ans = func(*args, **kwargs)
        end = datetime.now()
        print('%s ended at %s (took %s seconds)' % (func.__name__, end, (end - start).total_seconds()))
        return ans
    return wrapped

def get(domain, path):
    if ":" in domain:
        domain, port = domain.rsplit(":", 1)
    else:
        port = "80"
    s = subprocess.Popen(["telnet", domain, port], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    s.stdin.write(("GET " + path + " HTTP/1.0\n\n").encode("latin1"))
    s.stdin.flush()
    out = s.stdout.read().decode("latin1")
    return out.split("\r\n", 3)[-1]

class Node(list):
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = attrs
        self.style = HTML.parse_style(attrs.get("style", "")) if tag else {}
        self.parent = None

        self.x = None
        self.y = None
        self.w = None
        self.h = None
        self.tstyle = None

    def append(self, n):
        super(Node, self).append(n)
        n.parent = self

class HTML:
    Tag = collections.namedtuple("Tag", ["tag", "attrs"])

    @staticmethod
    def parse_attrs(tag):
        ts = tag.split(" ", 1)
        if len(ts) == 1:
            return tag, {}
        else:
            parts = ts[1].split("=")
            parts = [parts[0]] + sum([thing.rsplit(" ", 1) for thing in parts[1:-1]], []) + [parts[-1]]
            return ts[0], { a: b.strip("'").strip('"') for a, b in zip(parts[::2], parts[1::2]) }
    
    @staticmethod
    def parse_style(attr):
        return dict([x.strip() for x in y.split(":")] for y in attr.strip(";").split(";")) if ";" in attr or ":" in attr else {}
    
    @staticmethod
    def lex(source):
        source = " ".join(source.split())
        tag = None
        text = None
        for c in source:
            if c == "<":
                if text is not None: yield text
                text = None
                tag = ""
            elif c == ">":
                if tag is not None:
                    head, attrs = HTML.parse_attrs(tag.rstrip("/").strip())
                    yield HTML.Tag(head, attrs)
                    if tag.endswith("/"): yield HTML.Tag("/" + head, None)
                tag = None
            else:
                if tag is not None:
                    tag += c
                elif text is not None:
                    text += c
                else:
                    text = c
    
    def parse(tokens):
        path = [[]]
        style = []
        for tok in tokens:
            if isinstance(tok, HTML.Tag):
                if tok.tag.startswith("/"):
                    assert not tok.attrs
                    path.pop()
                    assert tok.tag == "/" + path[-1][-1].tag
                    if path[-1][-1].tag == "style":
                        assert len(path[-1][-1]) == 1
                        assert path[-1][-1][0].tag is None
                        style.append(path[-1][-1][0].attrs)
                        path[-1].pop()
                elif tok.tag == '!DOCTYPE':
                    pass
                else:
                    n = Node(tok.tag, tok.attrs)
                    path[-1].append(n)
                    path.append(n)
            else:
                path[-1].append(Node(None, tok))
        assert len(path) == 1, [t[-1].tag or t[-1].attrs for t in path]
        roots = [t for t in path[0] if t.tag]
        assert len(roots) == 1, [t.tag or t.attrs for t in roots]
        return roots[0], style

class CSS:
    @staticmethod
    def parse(source):
        i = 0
        while True:
            try:
                j = source.index("{", i)
            except ValueError as e:
                break
            
            sel = source[i:j].strip()
            i, j = j + 1, source.index("}", j)
            props = {}

            while i < j:
                try:
                    k = source.index(":", i)
                except ValueError as e:
                    break
                if k > j: break
                prop = source[i:k].strip()
                l = min(source.index(";", k + 1), j)
                val = source[k+1:l].strip()
                props[prop] = val
                if l == j: break
                i = l + 1
            yield sel, props
            i = j + 1
    
    @staticmethod
    def applies(sel, t):
        if t.tag is None:
            return False
        elif sel.startswith("."):
            return sel[1:] in t.attrs.get("class", "").split(" ")
        elif sel.startswith("#"):
            return sel[1:] == t.attrs.get("id", None)
        else:
            return sel == t.tag

    @staticmethod
    def px(val):
        return int(val.rstrip("px"))

def style(rules, t):
    for sel, props in reversed(rules):
        if CSS.applies(sel, t):
            for prop, val in props.items():
                t.style.setdefault(prop, val)
    for subt in t:
        style(rules, subt)

def inherit(t, prop, default):
    if t is None:
        return default
    else:
        return t.style[prop] if prop in t.style else inherit(t.parent, prop, default)

def layout(t, x, y):
    if t.tag is None:
        t.x, t.y, t.tstyle = x, y, t.parent.tstyle

        fs, weight, slant, decoration, color = t.tstyle
        font = tkFont.Font(family="Times", size=fs, weight=weight,
                           slant=slant, underline=(decoration == "underline"))
        for word in t.attrs.split():
            w = font.measure(word)
            if x + w > 800 - 2*8:
                y += fs * 1.75
                x = 8
            x += font.measure(word) + 6
        t.w = x - t.x
        t.h = y - t.y + fs * 1.75
    else:
        if "font-size" in t.style: fs = CSS.px(t.style["font-size"])
        if "margin-left" in t.style: x += CSS.px(t.style["margin-left"])
        if "margin-top" in t.style: y += CSS.px(t.style["margin-top"])

        if t.tag == "hr": y += int(t.attrs.get("width", "2"))

        t.x = x
        t.y = y
        t.tstyle = (CSS.px(inherit(t, "font-size", "16px")),
                    inherit(t, "font-weight", "normal"),
                    inherit(t, "font-style", "roman"),
                    inherit(t, "text-decoration", "none"),
                    inherit(t, "color", "black"))
            
        x_ = x
        for c in t:
            x_, y = layout(c, x_, y)
        if t.tag in "abi":
            t.w = x_ - x
            x = x_
        else:
            t.w = 800 - x

        if "margin-bottom" in t.style: y += CSS.px(t.style["margin-bottom"])
        if "margin-left" in t.style: x -= CSS.px(t.style["margin-left"])

        if t.tag in ["p", "h1", "h2", "h3", "li"]:
            y = t[-1].y + t[-1].h

        if t.tag in "abi":
            t.h = t[-1].h
        else:
            t.h = y - t.y

    return x, y

def render(canvas, t, scrolly):
    if t.tag is None:
        fs, weight, slant, decoration, color = t.tstyle
        font = tkFont.Font(family="Times", size=fs, weight=weight,
                           slant=slant, underline=(decoration == "underline"))

        x, y = t.x, t.y - scrolly
        for word in t.attrs.split():
            w = font.measure(word)
            if x + w > 800 - 2*8:
                y += 28
                x = 8
            canvas.create_text(x, y, text=word, font=font, anchor=tkinter.NW, fill=color)
            x += font.measure(word) + 6
    else:
        if t.tag == "li":
            x, y, fs, color = t.x - 16, t.y - scrolly, t.tstyle[0], t.tstyle[4]
            canvas.create_oval(x + 2, y + fs / 2 - 3, x + 7, y + fs / 2 + 2, fill=color, outline=color)
        elif t.tag == 'hr':
            x, y, color = t.x, t.y - scrolly, t.tstyle[4]
            width = int(t.attrs.get("width", "2"))
            canvas.create_line(x, y, 800 - x, y, width=width, fill=color)

        for subt in t:
            render(canvas, subt, scrolly=scrolly)
            

def chrome(canvas, url):
    canvas.create_rectangle(0, 0, 800, 60, fill='white')
    canvas.create_rectangle(10, 10, 35, 50)
    canvas.create_polygon(15, 30, 30, 15, 30, 45, fill='black')
    canvas.create_rectangle(40, 10, 65, 50)
    canvas.create_polygon(60, 30, 45, 15, 45, 45, fill='black')
    canvas.create_rectangle(70, 10, 110, 50)
    canvas.create_polygon(80, 30, 75, 30, 90, 15, 105, 30, 100, 30, 100, 45, 80, 45, 80, 30, fill='black')
    canvas.create_rectangle(115, 10, 795, 50)
    font = tkFont.Font(family="Courier New", size=25)
    canvas.create_text(120, 15, anchor=tkinter.NW, text=url, font=font)

def find_elt(t, x, y):
    for i in t:
        e = find_elt(i, x, y)
        if e is not None: return e
    if t.x <= x <= t.x + t.w and t.y <= y <= t.y + t.h:
        return t

class Browser:
    def __init__(self, url):
        self.source = None
        self.tree = None
        self.scrolly = 0
        self.home = url
        self.history = [url]
        self.index = 0
        with open("default.css") as f:
            self.default_style = list(CSS.parse(f.read()))
        
        window = tkinter.Tk()
        window.bind("<Down>", self.scroll(100))
        window.bind("<space>", self.scroll(400))
        window.bind("<Up>", self.scroll(-100))
        window.bind("<Button-1>", self.handle_click)
        window.focus_set()
        canvas = tkinter.Canvas(window, width=800, height=1000)
        canvas.pack(side=tkinter.LEFT)
        self.window = window
        self.canvas = canvas

    def fetch(self):
        url = self.history[self.index]
        assert url.startswith("http://")
        url = url[len("http://"):]
        domain, path = url.split("/", 1)
        response = get(domain, "/" + path)
        headers, source = response.split("\n\n", 1)
        self.source = source

    def parse(self):
        assert self.source
        tree, styles = HTML.parse(HTML.lex(self.source))
        rules = self.default_style
        for s in styles:
            rules.extend(list(CSS.parse(s)))
        style(rules, tree)
        layout(tree, x=8, y=8)
        self.tree = tree

    def scroll(self, by):
        def handler(e):
            self.scrolly = max(self.scrolly + by, 0)
            self.render()
        return handler

    @log_start_end_time
    def render(self):
        assert self.tree
        self.canvas.delete('all')
        render(self.canvas, self.tree, scrolly=self.scrolly - 60)
        chrome(self.canvas, self.history[self.index])

    def handle_click(self, e):
        if 10 <= e.x <= 35 and 10 <= e.y <= 50:
            self.index -= 1
            self.go()
        elif 40 <= e.x <= 65 and 10 <= e.y <= 50:
            self.index += 1
            self.go()
        elif 70 <= e.x <= 110 and 10 <= e.y <= 50:
            self.index = 0
            self.go()
        elif 115 <= e.x <= 795 and 10 <= e.y <= 50:
            print("location")
        else:
            e = find_elt(self.tree, e.x, e.y + self.scrolly - 60)
            while e is not None and e.tag != "a":
                e = e.parent
            if e is not None:
                url = e.attrs["href"]
                self.navigate(url)
            else:
                pass

    def navigate(self, url):
        self.history[self.index+1:] = [url]
        self.index += 1
        self.go()

    def go(self):
        self.scrolly = 0
        self.fetch()
        self.parse()
        self.render()

    def mainloop(self):
        self.window.mainloop()

if __name__ == "__main__":
    import sys
    b = Browser(sys.argv[1])
    b.go()
    b.mainloop()
