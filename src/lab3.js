class Text {
  constructor(text) {
  	this.text = text;
  }
}

class Tag {
  constructor(tag) {
  	this.tag = tag
  }
}

async function lex(body) {
  let out = [];
  let text = "";
  let in_tag = false;
  let prev_length = 0
  for (let c of body) {
    if (c == "<") {
      in_tag = true;
      if (text)
        out.push(new Text(text));
      text = "";
    } else if (c == ">") {
      in_tag = false;
      out.push(new Tag(text));
      text = "";
    } else {
      text += c;
    }
    if (out.length != prev_length) {
      await potentialBreakpointLex(out)
      prev_length = out.length
    }
  }
  if (!in_tag && text)
    out.push(new Text(text));
  return out;
}

let [WIDTH, HEIGHT] = [800, 600]
let [HSTEP, VSTEP] = [6, 18]

let SCROLL_STEP = 100

class Font {
  constructor(size, weight, style) {
  	this.size = size;
    this.weight = weight;
  	this.style = style;
  }

  toString() {
    return `${this.style} ${this.weight} ${this.size}px sans-serif`
  }

  textMetrics(text) {
  	let canvasElement = document.createElement('canvas');
  	document.body.appendChild(canvasElement);
    let canvasContext = canvasElement.getContext('2d');
    canvasContext.font = this.toString();
    document.body.removeChild(canvasElement);
    return canvasContext.measureText(text);
  }

  measure(text) {
    return this.textMetrics(text).width;
  }

  metrics() {
    let metrics = this.textMetrics(' ');
    return {
      ascent: metrics.fontBoundingBoxAscent,
      descent: metrics.fontBoundingBoxDescent
    };
  }
}

class Layout {
  constructor(tokens) {
  	this.tokens = tokens
  	this.display_list = []
  	this.cursor_x = HSTEP
  	this.cursor_y = VSTEP
  	this.weight = "normal"
  	this.style = "normal"
  	this.size = 16
    this.line = []
  }

  async layout() {
    for (let tok of this.tokens) {
      this.token(tok)
      await potentialBreakpointLayout(this.line, this.display_list);
    }
    this.flush();
    return this.display_list;
  }

  token(tok) {
    if (tok instanceof Text)
      this.text(tok.text)
    else if (tok.tag == "i")
      this.style = "italic"
    else if (tok.tag == "/i")
      this.style = "normal"
    else if (tok.tag == "b")
      this.weight = "bold"
    else if (tok.tag == "/b")
      this.weight = "normal"
    else if (tok.tag == "small")
      this.size -= 2
    else if (tok.tag == "/small")
      this.size += 2
    else if (tok.tag == "big")
      this.size += 4
    else if (tok.tag == "/big")
      this.size -= 4
    else if (tok.tag == "br")
      this.flush()
    else if (tok.tag == "/p") {
      this.flush()
      tok.cursor_y += VSTEP
    }
  }

  text(text) {
  	let font = new Font(
  		this.size,
  		this.weight,
  		this.style);
  	for (let word of text.split()) {
  	  let w = font.measure(word);
  	  if (this.cursor_x + w > WIDTH - HSTEP)
  		  this.flush();
  	  let cursor_x = this.cursor_x
      let entry = {
        x: cursor_x,
        word: word,
        font: font
      }
      this.line.push(entry);
  	  this.cursor_x += w + font.measure(' ')
  	}
  }

  flush() {
  	if (!this.line)
  	  return;
    let metrics = [];
    for (let entry of this.line) {
      metrics.push(entry.font.metrics())
    }

    let max_ascent = 0
    for (let metric of metrics) {
      if (metric.ascent > max_ascent)
        max_ascent = metric.ascent;
    }

  	let baseline = this.cursor_y + 1.2 * max_ascent

  	for (let entry of this.line) {
      // By default a CanvasRenderingContext2D draws relative to the
      // alphabetic baseline, so we don't need to adjust y. This is
      // different than the tkinter mode, which draws at top.
      /// CanvasRenderingContext2D can be switched modes via the 
      // textBaseline feature of CanvasRenderingContext2D, but the other
      // modes only make sense in languages that don't have a baseline
      // concept, such as CJK or Tibetan/Indic.
      // https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/textBaseline
  	  let y = baseline;
      let display_item = {
        x: entry.x,
        y: y,
        word: entry.word,
        font: entry.font
      };
  	  this.display_list.push(display_item)
  	}
  	this.cursor_x = HSTEP
  	this.line = []

    let max_descent = 0
    for (let metric of metrics) {
      if (metric.descent > max_descent)
        max_descent = metric.descent;
    }
  	this.cursor_y = baseline + 1.2 * max_descent
  }
}

class Browser {
  constructor(canvasElement) {
    this.canvasElement = canvasElement;
    const rectangle = canvasElement.getBoundingClientRect();
    canvasElement.width = rectangle.width * devicePixelRatio;
    canvasElement.height = rectangle.height * devicePixelRatio;
    this.canvasContext = canvasElement.getContext('2d');
    this.scroll = 0
  }

  async load(body) {
    this.clearCanvas();
    let tokens = await lex(body);
    let layout = new Layout(tokens);
    this.display_list = await layout.layout();
    await this.render();
  }

  clearCanvas() {
    this.canvasContext.clearRect(0, 0, this.canvasElement.width,
        this.canvasElement.height);
  }

  async render() {
    let count = 0;
    for (let entry of this.display_list) {
      let {x, y, word, font} = entry;
      if (y > this.scroll + HEIGHT)
        continue;
      let metrics = font.metrics()
      let line_height = metrics.ascent + metrics.descent
      if (y + line_height < this.scroll)
        continue;

      this.canvasContext.font = entry.font.toString();
      console.log('font: ' + entry.font.toString());
      this.canvasContext.fillText(word, x, y - this.scroll);
      await potentialBreakpointRender(count++);
    }
  }

  scrolldown() {
    this.scroll += SCROLL_STEP;
    this.render()
  }
}