// One-page resume. Data comes from scripts/build.py (sys.inputs.data); edit cwhash.yaml, not this file's content.
#let d = json(bytes(sys.inputs.data))

#set document(title: d.name + " — Resume", author: d.name, date: none)
#set page(paper: "a4", margin: (x: 2cm, y: 1.8cm))
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "en")
#set par(leading: 0.55em)

#let section(title) = block(above: 1.3em, below: 0.6em)[
  #text(size: 9.5pt, weight: "bold", tracking: 0.12em, upper(title))
  #v(-0.7em)
  #line(length: 100%, stroke: 0.5pt)
]

#let entry(title, org, when) = block(above: 0.55em, below: 0.55em, grid(
  columns: (1fr, auto),
  column-gutter: 1em,
  [*#title*#if org != "" [, #org]],
  align(right, when),
))

// Header
#align(center)[
  #text(size: 20pt, weight: "bold", d.name)
  #v(-0.4em)
  #link("mailto:" + d.email, d.email) #h(0.4em)·#h(0.4em) #link(d.linkedin, d.linkedinText)
  #v(-0.4em)
  #text(style: "italic")[Open to #d.openTo.join(", ")]
]

#section("Education")
#for e in d.education { entry(e.title, e.org, e.when) }

#section("Experience")
#for e in d.experience { entry(e.title, e.org, e.when) }

#section("Capstone Project")
#d.capstone

#section("Awards")
#for a in d.awards { entry(a.title, a.org, a.when) }

#section("Skills")
#grid(
  columns: (auto, 1fr),
  column-gutter: 1.2em,
  row-gutter: 0.6em,
  ..d.stack.map(s => ([*#s.label*], s.items.join(", "))).flatten(),
)
