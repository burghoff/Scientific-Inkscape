# Best practices for exporting

Exporting figures to a format that always looks good can be tricky. There can be issues at every stage: some typesetting software does a poor job maintaining the integrity of your figures, some publishers will make undesired modifications to your figures, and some document renderers will do a poor job displaying your figures. Your job as a writer is to worry about *all of them*.

The most reliable way to ensure that the integrity of your figures is preserved is to convert them to high-resolution (600 DPI) bitmaps. As long as they are not downsampled or converted into JPG, they will look the same on almost every machine. The tradeoff is that in large documents and presentations you will end up with large file sizes, you won't be able to select text from the figures, and at high zooms they will look bad. Furthermore, they essentially become uneditable.

I prefer to maintain figures in a vector format most similar to the original for as long as possible. This document discusses how to do that.

## Microsoft Office

In general, Word and Powerpoint have poor support for vector graphics. Historically the only way to add vector graphics to a document was to use the EMF format, which lacks transparency and a number of other essential features. The more recent versions of Office finally added SVG support, but as of this writing it is buggy and unreliable, often failing to properly render text and raster images. The best way to insert graphics is to use the Autoexporter to make a **Portable SVG.** Portable SVGs are SVGs that have been simplified to avoid some of the common rendering bugs that occur in external programs. For example:
<p align="center"><img src="https://github.com/burghoff/Scientific-Inkscape/blob/main/examples/Sterczewski_comparisons_portable.svg" alt="drawing" ></img></p>
Text from a normal SVG is rendered very poorly by Powerpoint, while the EMF has lost its transparency. However, the Portable SVG is rendered well most of the time. If you notice a problematic element, you can mark it for Rasterization—this will rasterize just that element while leaving the rest of the vector graphics intact.

## LaTeX and Overleaf

LaTeX has long supported vector graphics. Currently, it is recommended that you export your figures as PDFs. The Autoexporter can make this process automatic: if you store your SVGs somewhere and have the Autoexporter automatically write the exports to your LaTeX document's directory, changes to your SVGs will automatically be reflected in your final document. If you use Overleaf, you can do this by linking your Overleaf account to a Dropbox account.

