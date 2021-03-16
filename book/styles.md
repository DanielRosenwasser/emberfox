---
title: Applying User Styles
chapter: 6
cur: styles
prev: layout
next: chrome
...

So far, the appearance of the various elements has been fixed. But web
pages should be able to override our style decisions and take on a
unique character. This is done via CSS.

The `style` attribute
=====================

Different elements have different styles, like margins for paragraphs
and borders for code blocks. Those styles are assigned by our browser,
and it *is* good to have some defaults. But webpages should be able to
override those choices.

The simplest mechanism for that is the `style` attribute on elements.
It looks like this:

``` {.example}
<div style="margin-left:10px;margin-right:10px;"></div>
```

It's a `<div>` element with its `style` attribute set. That attribute
contains two key-value pairs, which set `margin-left` and
`margin-right` to 10 pixels each.^[CSS allows spaces around the
punctuation, but our attribute parser does not support it.] We want to
store these pairs in a `style` field on the `ElementNode` so we can
consult them during layout:[^python-get]

[^python-get]: The `get` method for dictionaries gets a value out of a
    dictionary, or uses a default value if it's not present.

``` {.python}
class ElementNode:
    def __init__(self, tag, parent, attributes):
        # ...
        self.style = {}
        for pair in self.attributes.get("style", "").split(";"):
            if ":" not in pair: continue
            prop, val = pair.split(":")
            self.style[prop.strip().lower()] = val.strip()
```

Each `ElementNode` now has a `style` field with any stylistic choices
made by the author. Let's add support for *margins*, *borders*, and
*padding*, which change the position of block layout objects. Here's
how those work. In effect, every block has four rectangles associated
with it: the *margin rectangle*, the *border rectangle*, the *padding
rectangle*, and the *content rectangle*:

![](https://www.w3.org/TR/CSS2/images/boxdim.png)

So far, our block layout objects have had just one size and position;
these will refer to the border rectangle (so that the `x` and `y`
fields point to the top-left corner of the outside of the layout
object's border). To track the margin, border, and padding, we'll also
store the margin, border, and padding widths on each side of the
layout object in the variables `mt`, `mr`, `mb,` and `ml`; `bt`, `br`,
`bb`, and `bl`; and `pt`, `pr`, `pb`, and `pl`. The naming convention
here is that the first letter stands for margin, border, or padding,
while the second letter stands for top, right, bottom, or left.

Since each block layout object now has more variables, we'll need to
add code to `layout` to compute them:

``` {.python}
def px(s):
    if s.endswith("px"):
        return int(s[:-2])
    else:
        return 0

class BlockLayout:
    def layout(self):
        self.mt = px(self.node.style.get("margin-top", "0px"))
        self.bt = px(self.node.style.get("border-top-width", "0px"))
        self.pt = px(self.node.style.get("padding-top", "0px"))
        # ... repeat for the right, bottom, and left edges
```

Remember to write out the code to access the other 9 properties, and
don't forget that the border one is called `border-X-width`, not
`border-X`.[^because-colors]

[^because-colors]: Because borders have not only widths but also
    colors and styles, while paddings and margins are thought of as
    whitespace, not something you draw.

You'll also want to add these twelve variables to `DocumentLayout` and
`InlineLayout` objects. Set them all to zero.

With their values now loaded, we can use these fields to drive layout.
First of all, when we compute width, we need to account for the space
taken up by the parent's border and padding; and likewise we'll need
to adjust each layout object's `x` and `y` based on its margins:[^backslash-continue]

[^backslash-continue]: In Python, if you end a line with a backslash,
    the newline is ignored by the parser, letting you split a logical
    line of code across two actual lines in your file.

``` {.python}
def layout(self):
    # ...
    self.w = self.parent.w - self.parent.pl - self.parent.pr \
        - self.parent.bl - self.parent.br \
        - self.ml - self.mr
    self.y += self.mt
    self.x += self.ml
    # ...
```

Similarly, when we position child layout objects, we'll need to
account for our their parent's border and padding:

``` {.python indent=4}
def layout(self):
    # ...
    y = self.y
    for child in self.children:
        child.x = self.x + self.pl + self.bl
        child.y = y
        child.layout()
        y += child.mt + child.h + child.mb
    self.h = y - self.y
```

Likewise, in `InlineLayout` we'll need to account for the parent's
padding and border:

``` {.python}
class InlineLayout:
    def layout(self):
        self.w = self.parent.w - self.parent.pl - self.parent.pr \
            - self.parent.bl - self.parent.br
```

It's now possible to indent a single element by giving it a `style`
attribute that adds a `margin-left`. But while that's good for one-off
changes, it is a tedious way to change the style of, say, every
paragraph on the page. And if you have a site with many pages, you'll
need to remember to add the same `style` attributes to every web page
to achieve a measure of consistency. CSS provides a better way.

Parsing CSS
===========

In the early days of the web,^[I'm talking Netscape 3. The late 90s.]
the element-by-element approach was all there was.^[Though back then
it wasn't the `style` attribute, it was a custom elements like `font`
and `center`.] CSS was invented to improve on this state of affairs:

-   CSS files can adjust styling of many elements at once
-   CSS files can style multiple pages from a single file
-   CSS is future-proof and supports browsers with different features

To achieve these goals, CSS extends the key-value `style` attribute
with two connected ideas: *selectors* and *cascading*. In CSS, you
have blocks of style information, but those blocks apply to *multiple
elements*, specified using a selector:

``` {.css}
selector {
    property-1: value-1;
    property-2: value-2;
    property-3: value-3;
    ...
}
```

To account for the possibility that several blocks apply to a single
element, there's a *cascading* mechanism to resolve conflicts in favor
of the most specific rule.

To support CSS in our browser, we'll need to:

- Parse CSS files to understand the selector for each block and also
  the property values that block sets;
- Run each selector to figure out which elements on the page each
  block selects;
- Add the block's property values to those elements' `style` fields.

Let's start with the parsing. I'll use recursive *parsing functions*,
each parsing a certain type of CSS element like selectors, properties,
or blocks. Parsing function will take an index into the input and
return a new index, plus the data it parsed. Since we'll have a lot of
parsing functions, let's organize them in a `CSSParser` class:

``` {.python}
class CSSParser:
    def __init__(self, s):
        self.s = s
```

The class wraps the string we're parsing. Parsing functions access the
string through `self.s`. Let's start small and build up. A parsing
function for whitespace would look like this:

``` {.python}
def whitespace(self, i):
    while i < len(self.s) and self.s[i].isspace():
        i += 1
    return None, i
```

This parsing function takes index `i`, pointing to the part of the
string we are currently parsing, and increments it through every
whitespace character. It then returns the new value of `i` that points
to a non-whitespace character. Whitespace is insignificant, so it
returns `None` for the parsed data.

Parsing functions can also fail. For example, it's often helpful to
check that there's a certain piece of text at the current location:

``` {.python}
def literal(self, i, literal):
    assert self.s[i:i+len(literal)] == literal
    return None, i + len(literal)
```

Here the check is done by `assert`, which raises an exception if the
condition is false.[^add-a-comma]

[^add-a-comma]: Add a comma after the condition, and you can add some
    error text to the assertion. I recommend doing that for all of
    your assertions to help in debugging.

Parsing functions can also return data. For example, to parse CSS
properties and values, we'll use:

``` {.python}
def word(self, i):
    j = i
    while j < len(self.s) and self.s[j].isalnum() or self.s[j] in "-.":
        j += 1
    assert j > i
    return self.s[i:j], j
```

This function takes index `i` pointing to the start of the value and
returns index `j` pointing to its end. It computes `j` by advancing
through letters, numbers, and minus and period characters (which might
be present in numbers), and returns all the text it iterated through
as the parsed data. Also note the check: if `j` didn't advance, that
means `i` didn't point at a word to begin with.

Parsing functions can also build upon one another. Property-value
pairs, for example, are a word, a colon, and another
word,[^technically-different] with whitespace in between:

[^technically-different]: In reality properties and values have
    different syntaxes, so using `word` for both isn't quite right,
    but our browser supports few enough values in our parser that this
    simplification will be alright.

``` {.python}
def pair(self, i):
    prop, i = self.word(i)
    _, i = self.whitespace(i)
    _, i = self.literal(i, ":")
    _, i = self.whitespace(i)
    val, i = self.word(i)
    return (prop.lower(), val), i
```

This builds upon `word`, `whitespace`, and `literal` to build a more
complicated parsing function. And note that if
`i` does not actually point to a property-value pair, one of the
`word` calls, or the `literal` call, will fail. When we parse rule
bodies, we can catch this error to skip property-value pairs that
don't parse:

``` {.python indent=4}
def body(self, i):
    pairs = {}
    _, i = self.literal(i, "{")
    _, i = self.whitespace(i)
    while i < len(self.s) and self.s[i] != "}":
        try:
            (prop, val), i = self.pair(i)
            pairs[prop] = val
            _, i = self.whitespace(i)
            _, i = self.literal(i, ";")
        except AssertionError:
            _, i = self.ignore_until(i, [";", "}"])
            if i < len(self.s) and self.s[i] == ";":
                _, i = self.literal(i, ";")
        _, i = self.whitespace(i)
    _, i = self.literal(i, "}")
    return pairs, i
```

This parsing function introduces a few new tricks. First, it has a
while loop to collect multiple property-value pairs into a dictionary.
Secondly, it uses a `try` block to catch exceptions from malformed
property-value pairs. When a malformed pair is seen, it uses this
`ignore_until` function:

``` {.python}
def ignore_until(self, i, chars):
    while i < len(self.s) and self.s[i] not in chars:
        i += 1
    return None, i
```

Skipping parse errors is a double-edged sword. It hides error
messages, so debugging CSS files becomes more difficult, and also
makes it harder to debug your parser.[^try-no-try] This makes
"catch-all" error handling like this a code smell in most cases.

[^try-no-try]: Try debugging without the `try` block first.

However, on the web there is an unusual benefit: it supports an
ecosystem of multiple implementations. For example, different browsers
may support different syntaxes for property values.[^like-parens]
Thanks to silent parse errors, web pages can use features that only
some browsers support, with other browsers just ignoring it. This
principle variously called "Postel's Law",[^for-jon] the "Digital
Principle",[^from-circuits] or the "Robustness Principle": produce
maximally supported output but accept unsupported input.

[^like-parens]: Our browser does not support parentheses in property
    values, which are valid in real browsers, for example.
    
[^for-jon]: After a line in the specification of TCP, written by Jon
    Postel

[^from-circuits]: After a similar idea in circuit design, where
    transistors must be nonlinear to reduce analog noise.

Finally, to parse a full CSS rule, we need to parse selectors. Selectors
come in multiple types; for now, our browser will support three:

- Tag selectors: `p` selects all `<p>` elements, `ul` selects all
  `<ul>` elements, and so on.
- Class selectors: HTML elements have a `class` attribute, which is a
  space-separated list of arbitrary names, so the `.foo` selector
  selects the elements that have `foo` in that list.
- ID selectors: `#main` selects the element with an `id` value of
  `main`.

We'll start by defining some data structures for selectors:^[I'm
calling the `ClassSelector` field `cls` instead of `class` because
`class` is a reserved word in Python.]

``` {.python}
class TagSelector:
    def __init__(self, tag):
        self.tag = tag

class ClassSelector:
    def __init__(self, cls):
        self.cls = cls

class IdSelector:
    def __init__(self, id):
        self.id = id
```

We now want parsing functions for each of these data structures.
That'll look like:

``` {.python indent=4}
def selector(self, i):
    if self.s[i] == "#":
        _, i = self.literal(i, "#")
        name, i = self.word(i)
        return IdSelector(name), i
    elif self.s[i] == ".":
        _, i = self.literal(i, ".")
        name, i = self.word(i)
        return ClassSelector(name), i
    else:
        name, i = self.word(i)
        return TagSelector(name.lower()), i
```

While I'm using `word` for tag, class, and identifier names (a
simplification a real browser couldn't do) I'm at least being careful
to tag names case-insensitive.

Finally, selectors and bodies can be combined:

``` {.python}
def rule(self, i):
    selector, i = self.selector(i)
    _, i = self.whitespace(i)
    body, i = self.body(i)
    return (selector, body), i
```

Finally, a CSS file itself is just a sequence of rules:

``` {.python indent=4}
def file(self, i):
    rules = []
    _, i = self.whitespace(i)
    while i < len(self.s):
        try:
            rule, i = self.rule(i)
            rules.append(rule)
        except AssertionError:
            _, i = self.ignore_until(i, "}")
            _, i = self.literal(i, "}")
        _, i = self.whitespace(i)
    return rules, i
```

With all our parsing functions written, we can give the `CSSParser`
function a simple entry point:

``` {.python}
class CSSParser:
    def parse(self):
        rules, _ = self.file(0)
        return rules
```

Make sure to test your parser, like you did the [HTML parser](html.md)
two chapters back. If you find an error, the best way to proceed is to
print the index at the beginning of every parsing function, and print
both the index and parsed value at the end. You'll get a lot of
output, but if you step through it by hand, you will find your mistake.

Once we've parsed a CSS file, we need to apply it to the elements on
the page.

Selecting styled elements
=========================

Our next step, after parsing CSS, is to figure out which elements each
rule applies to. The easiest way to do that is to add a method to the
selector classes, which tells you if the selector matches. Here's what
it looks like for `ClassSelector`:

``` {.python}
def matches(self, node):
    return self.cls in node.attributes.get("class", "").split()
```

You can write `matches` for `TagSelector` and `IdSelector` on your
own.

Now that we know which rules apply to an element, we need use their
property-value pairs to change its `style`. The logic is pretty
simple:

-   Recurse over the tree of `ElementNode`s;
-   For each rule, check if the rule matches;
-   If it does, go through the property/value pairs and assign them.

Here's what the code would look like:

``` {.python replace=return/node.style%20=%20node.parent.style}
def style(node, rules):
    if isinstance(node, TextNode):
        return
    else:
        for selector, pairs in rules:
            if selector.matches(node):
                for property in pairs:
                    if property not in node.style:
                        node.style[property] = pairs[property]
        for child in node.children:
            style(child, rules)
```

We're skipping `TextNode` objects because text doesn't have styles in
CSS (just the elements that wrap the text).

Note that we skip properties that already have a value. That's because
`style` attributes are loaded into the `style` field first, and should
take priority. But it means that it matters what order you apply the
rules in.

What's the correct order? In CSS, it's called *cascade order*, and it
is based on the selector used by the rule. Tag selectors get the
lowest priority; class selectors one higher; and id selectors higher
still. Just like how the `style` attribute comes first, we need to
sort the rules in priority order, with higher-priority rules first.

So let's add a `priority` method to the selector classes that return
this priority. In this simplest implementation the exact numbers don't
matter if they sort right, but with an eye toward the future let's
assign tag selectors priority `1`, class selectors priority `16`, and
id selectors priority `256`:

``` {.python}
class TagSelector:
    def priority(self):
        return 1
        
class ClassSelector:
    def priority(self):
        return 16
        
class IdSelector:
    def priority(self):
        return 256
```

Now, before you call `style`, you should sort your list of rules:

``` {.python}
rules.sort(key=lambda x: x[0].priority())
rules.reverse()
```

Note the `reverse` call: we want higher-priority rules to come first.
In Python, the `sort` function is *stable*, which means that things
keep their relative order if possible. This means that in general, a
later rule has higher priority, unless the selectors used force
something different.

Downloading styles
==================

Browsers get CSS code from two sources. First, each browser ships with
a *browser style sheet*,[^technically-ua] which defines the default
styles for all sorts of elements; second, browsers download CSS code
from the web, as directed by web pages they browse to. Let's start
with the browser style sheet.

[^technically-ua]: Technically called a "user agent" style sheet,
    because the browser acts as an agent of the user.

Our browser's style sheet might look like this:

``` {.css}
p { margin-bottom: 16px; }
ul { margin-top: 16px; margin-bottom: 16px; padding-left: 20px; }
li { margin-bottom: 8px; }
pre {
    margin-top: 8px; margin-bottom: 8px;
    padding-top: 8px; padding-right: 8px;
    padding-bottom: 8px; padding-left: 8px;
}
```

Our CSS parser can convert this CSS source code to text:

``` {.python replace=browser.css/browser6.css}
class Browser:
    def load(self, url):
        header, body = request(url)
        nodes = parse(lex(body))

        with open("browser.css") as f:
            rules = CSSParser(f.read()).parse()
```

Beyond the browser styles, our browser needs to find website-specific
CSS files, download them, and use them as well. Web pages call out
their CSS files using the `link` element, which looks like this:

``` {.example}
<link rel="stylesheet" href="/main.css">
```

The `rel` attribute here tells that browser that this is a link to a
stylesheet. Browsers mostly don't care about any [other kinds of
links][link-types], but search engines do[^like-canonical], so `rel`
is mandatory.

[^like-canonical]: For example, `rel=canonical` names the "master
    copy" of a page and is used by search engines to track pages that
    appear at multiple URLs.

[link-types]: https://developer.mozilla.org/en-US/docs/Web/HTML/Link_types

To find these links, we'll need another recursive function:

``` {.python}
def find_links(node, lst):
    if not isinstance(node, ElementNode): return
    if node.tag == "link" and \
       node.attributes.get("rel", "") == "stylesheet" and \
       "href" in node.attributes:
        lst.append(node.attributes["href"])
    for child in node.children:
        find_links(child, lst)
    return lst
```

For each link, the `href` attribute gives a location for the
stylesheet in question. The browser is expected to make a GET request
to that location, parse the stylesheet, and use it. Note that the
location is not a full URL; it is something called a *relative URL*,
which can come in three flavors:^[There are even more flavors,
including query-relative and scheme-relative URLs, that I'm skipping.]

-   A normal URL, which specifies a scheme, host, path, and so on
-   A host-relative URL, which starts with a slash but reuses the
    existing scheme and host
-   A path-relative URL, which doesn't start with a slash and is
    resolved like a file name would be[^how-file]
    
[^how-file]: The "file name" after the last slash of the current URL
    is dropped; if the relative URL starts with "../", slash-separated
    "directories" are dropped from the current URL; and then the
    relative URL is put at the end.

To turn a relative URL into a full URL, then, we need to figure out
which case we're in:

``` {.python}
def relative_url(url, current):
    if "://" in url:
        return url
    elif url.startswith("/"):
        return "/".join(current.split("/")[:3]) + url
    else:
        current = current.rsplit("/", 1)[0]
        while url.startswith("../"):
            current = current.rsplit("/", 1)[0]
            url = url[3:]
        return current + "/" + url
```

In the second case, the `[:3]` and the `"/".join` handle the two
slashes that come after `http:` in the URL, while in the last case,
the logic ensures that a link to `foo.html` on `http://a.com/bar.html`
goes to `http://a.com/foo.html`, not `http://a.com/bar.html/foo.html`.

Let's put it all together. We want to collect CSS rules from each of
the linked files, and the browser style sheet, into one big list so we
can apply each of them. So let's add them onto the end of the `rules`
list:

``` {.python}
def load(self, url):
    # ...
    for link in find_links(nodes, []):
        header, body = request(relative_url(link, url))
        rules.extend(CSSParser(body).parse())
```

Since the page's stylesheets come *after* browser style, user styles
take priority over the browser style sheet.^[In reality this is
handled by browser styles having a lower score than user styles in the
cascade order, but our browser style sheet only has tag selectors in
it, so every rule already has the lowest possible score.] With the
rules loaded, we need only sort and apply them and then do layout:

``` {.python}
def load(self, url):
    # ...
    rules.sort(key=lambda x: x[0].priority())
    rules.reverse()
    style(nodes, rules)
    self.layout(nodes)
```

With this done, each page should now automatically apply the margins
and paddings specified in the browser stylesheet, making it possible
to delete some of `InlineLayout`'s tag handlers in its `close` method.

Inherited styles
================

Our implementation of margins, borders, and padding styles only affect
the block layout mode.[^inline-margins] We'd like to extend CSS to
affect inline layout mode as well, for example to change text styling.
But there's a catch: inline layout is mostly concerned with text, but
text nodes don't have any styles at all. How can that work?

[^inline-margins]: Margins, borders, and padding can be applied to
    inline layout objects in a real browser, but they work in a kind
    of funky way.

The solution in CSS is *inheritance*. Inheritance means that if some
node doesn't have a value for a certain property, it uses its
parent's value instead. Some properties are inherited and some
aren't; it depends on the property: the margin, border, and padding
properties aren't inherited, but the font properties are.

Let's implement three inherited properties: `font-weight` (which can
be `normal` or `bold`), `font-style` (which can be `normal` or
`italic`), and `font-size` (which can be any pixel value). To inherit
a property, we need to check, after all the rules and inline styles
have been applied, whether the property is set and, if it isn't, to
use the parent node's style. To begin with, let's list our inherited
properties and their default values:

``` {.python}
INHERITED_PROPERTIES = {
    "font-style": "normal",
    "font-weight": "normal",
    "font-size": "16px",
}
```

Now let's add another loop to `style`, *after* the handling of rules
but *before* the recursive calls, to inherit properties:

``` {.python}
def style(node, rules):
    # ...
    for property, default in INHERITED_PROPERTIES.items():
        if property not in node.style:
            if node.parent:
                node.style[property] = node.parent.style[property]
            else:
                node.style[property] = default
    # ...
```

Because this loop comes *before* the recursive call, the parent has
already inherited the correct property value when the children try to
read it.

On `TextNode` objects we can do an even simpler trick, since a text
node never has styles of its own and only inherits from its parent:

``` {.python}
def style(node, rules):
    if isinstance(node, TextNode):
        node.style = node.parent.style
    else:
        # ...
```

With `font-weight` and `font-style` set on every node, `InlineLayout`
no longer needs `style`, `weight`, and `size` fields; they were only
there to track when text was inside or outside `<i>` and `<b>` tags,
and now styles and inheritance are doing that job:

``` {.python}
class InlineLayout:
    def font(self, node):
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(px(node.style["font-size"]) * .75)
        return tkinter.font.Font(size=size, weight=weight, slant=style)
    
```

Note that the `font-style` needs to replace the CSS default of
"normal" with the Tk value "roman", and the `font-size` needs to be
converted from pixels to points.[^72ppi]

[^72ppi]: Normally you think of points as a physical length unit (one
    72^nd^ of an inch) and pixels as a digital unit (dependent on the
    screen) but in CSS, the conversion is fixed at exactly 75% (or 96
    pixels per inch). The goal is device-independence, though it seems
    weird to me and it does cause problems.

To use this new `font` method, we need `text` to take a `TextNode` as
input, not just the text inside of it, so that `text` has access to
the element style:

``` {.python}
class InlineLayout:
    def recurse(self, node):
        if isinstance(node, TextNode):
            self.text(node)
        else:
            for child in node.children:
                self.recurse(child)

    def text(self, node):
        font = self.font(node)
        for word in node.text.split():
            # ...
```

Now support for the `i`, `b`, `small`, and `big` tags can all be moved
to CSS:

``` {.css}
i { font-style: italic; }
b { font-weight: bold; }
small { font-size: 12px; }
big { font-size: 20px; }
```

Another place where the code depends on specific tag names is
`layout_mode`, which relies on the list `BLOCK_ELEMENTS` of block
element tag names. The CSS `display` property, which can be either
`block` or `inline`, replaces that mechanism.[^lots-of-values] So we
can add all the block elements to our browser style sheet:

[^lots-of-values]: Modern CSS adds way more values to this property,
like `run-in` or `inline-block` or `flex` or `grid`, and it has layout
modes set by other properties, like `float` and `position`. These
values support layouts you couldn't do with just `block` and `inline`,
and people really care about making their web pages look good.

``` {.css}
html { display: block; }
body { display: block; }
/* ... */
```

And then read that in `layout_mode`:

``` {.python}
def layout_mode(node):
    # ...
    for child in node.children:
        # ...
        elif child.style.get("display", "inline") == "block":
            has_containers = True
        # ...
    # ...
```

With these changes, `InlineLayout` can lose its `open` and `close`
methods, becoming a small, self-contained engine for line layout while
most of its domain-specific knowledge of tags is moved to the browser
style sheet.

That style sheet is easier to edit, since it's independent of the rest
of the code. And while sometimes moving things to a data file means
maintaining a new format, here we get to reuse a format, CSS, that our
browser needs to support anyway.

Summary
=======

This chapter implemented a rudimentary but complete styling engine,
including downloading, parser, matching, sorting, and applying CSS
files. That means we:

- Added styling support in both `style` attributes and `link`ed CSS files;
- Implemented for margins, borders, and padding to block layout objects;
- Refactored `InlineLayout` to move the font properties to CSS;
- Removed most tag-specific reasoning from our layout code.

Our styling engine is also relatively easy to extend with properties
and selectors.

Exercises
=========

*Shorthand Properties*: CSS "shorthand properties" set multiple
related CSS properties at the same time; for example, `margin: 10px`
sets all four margin properties to `10px`, while `margin: 1px 2px 3px
4px` sets the top, right, bottom, and left margins to one, two, three,
and four pixels respectively. Implement the `margin`, `padding`,
`border-width`, and `font` shorthands as part of the parser.

*Selector Groups*: CSS allows grouping multiple rules, all with the
same body, by listing all their selectors with commas in between. For
example, `b, strong { font-weight: bold }` makes both the `b` and
`strong` tags bold. Implement this as part of your parser and use it
to shorten and shorten the browser style sheet.

*Width/Height*: Add support to block layout objects for the `width`
and `height` properties. These can either be a pixel value, which
directly sets the width or height of the layout object, or the word
`auto`, in which case the existing layout algorithm is used.

*Percentages*: Most places where you can specify a pixel value in CSS,
you can also write a percentage value like `50%`. When you do that for
`margin`, `border`, or `padding` properties, it's relative to the
layout object's width, while when you do it for `font-size` it's
relative to the parent's font size. Implement percentage values for
all of these properties.

*Selector Sequences*: Sometimes you want to select an element by tag
*and* class. You do this by concatenating the selectors without
anything in between:[^no-ws] `span.announce` selects elements that
match both `span` and `.announce`. Implement a new `SelectorSequence`
class to represent these and modify the parser to parse them. Sum
priorities.[^lexicographic]

[^no-ws]: Not even whitespace!

[^lexicographic]: Priorities for `SelectorSequence`s are supposed to
    compare the number of ID, class, and tag selectors in
    lexicographic order, but summing the priorities of the selectors
    in the sequence will work fine as long as no one strings more than
    16 selectors together.

*Descendant Selectors*: When multiple selectors are separated with
spaces, like `ul b`, that selects all `<b>` elements with a `<ul>`
ancestor. Implement descendent selectors; scoring for descendent
selectors works just like for combination selectors. Make sure that
something like `section .warning` selects warnings inside sections,
while `section.warning` selects warnings that *are* sections.

*Ancestor Selectors*: an ancestor selector is the inverse of a descendant
selector - it styles an ancestor according to the presence of a descendant.
This feature is one of the benefits provided by the
[`:has` syntax](https://drafts.csswg.org/selectors-4/#relational). However, you
will find that `:has` is not implemented in any real browser as yet. Can you
guess why? Hint: try to implement ancestor selectors and analyze the speed of
your algorithm.
