# Best practices for exporting

Exporting figures to a format that always looks good can be tricky. There can be issues at every stage: some typesetting software does a poor job maintaining the integrity of your figures, some publishers will make undesired modifications to your figures, and some document renderers will do a poor job displaying your figures. Your job as a writer is to worry about *all of them*.

The most reliable way to ensure that the integrity of your figures is preserved is to convert them to high-resolution (600 DPI) bitmaps. As long as they are not downsampled or converted into JPG, they will look the same on almost every machine. The tradeoff is that in large documents and presentations you will end up with large file sizes, you won't be able to select text from the figures, and at high zooms they will look bad. Furthermore, they essentially become uneditable.

My preference is to try to maintain figures in a vector format most similar to the original for as long as possible. This document discusses how to do that.

## Microsoft Office

In general, Word and Powerpoint have poor support for vector graphics. Historically the only way to add vector graphics to a document was to use the EMF format, which lacks transparency and a number of other essential features. The more recent versions of Office finally added SVG support, but as of this writing it is buggy and unreliable, often failing to properly render text and raster images. The best way to insert graphics is to use the Autoexporter to **export an Optimized SVG** with the "Optimize SVGs by converting to PDF and back" option selected.
