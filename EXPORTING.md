# Best practices for exporting

Exporting figures to a format that always looks good can be tricky. There can be issues at every stage: some typesetting software does a poor job maintaining the integrity of your figures, some publishers will make undesired modifications to your figures, and some document renderers will do a poor job displaying your figures. Your job as a writer is to worry about *all of them*.

The most reliable way to ensure that the integrity of your figures is preserved is to convert them to high-resolution (600 DPI) bitmaps. As long as they are not downsampled or converted into JPG, they will look the same on almost every machine. The tradeoff is that in large documents and presentations you will end up with large file sizes, you won't be able to select text from the figures, and at high zooms they will look bad. Furthermore, they essentially become uneditable.

If you want to maintain your figures in a vector format most similar to the original for as long as possible, this document tells you how.

## Document types
### Microsoft Office
In general, Word and Powerpoint have poor support for vector graphics. Historically the only way to add vector graphics to a document was to use the EMF format, which lacks transparency and a number of other essential features. The more recent versions of Office finally added SVG support, but as of this writing it is buggy and unreliable, often failing to properly render text and raster images. The best way to insert graphics is to use the Autoexporter to make a **Plain SVG.** Plain SVGs are SVGs that have been simplified to avoid some of the common rendering bugs that occur in external programs. For example:
<p align="center"><img src="https://github.com/burghoff/Scientific-Inkscape/blob/main/examples/Sterczewski_comparisons_plain.svg" alt="drawing" ></img></p>
Text from a normal SVG is rendered very poorly by Powerpoint, while the EMF has lost its transparency. However, the Plain SVG is rendered well most of the time. If you notice a problematic element, you can mark it for Rasterization—this will rasterize just that element while leaving the rest of the vector graphic intact.

### LaTeX and Overleaf
LaTeX intrinsically supports vector graphics and has excellent support for PDFs. The Autoexporter was actually designed with LaTeX in mind and makes this convenient. If you store your SVGs somewhere and have the Autoexporter automatically write the exports to your LaTeX document's directory, changes to your SVGs will automatically be reflected in your final document. If you use Overleaf, you can do this by linking your Overleaf account to a Dropbox account.

## Object-specific considerations

### Paths
Paths are the most fundamental element of any vector drawing, and every renderer supports them. However, some renderers do a better job than others. Even though it was Adobe that introduced the PDF, their PDF viewing software is amongst the worst. The reason is that they have a default setting euphemistically called "Enhance thin lines" whose main purpose is to make single-pixel lines thick. This appears to have been introduced in the 90s when most documents were viewed on CRT monitors, and single-pixel lines could disappear. The strongly-recommended "Prevent thin line enhancement" option of the Autoexporter prevents this from ever happening; see the example screenshots below:
<p align="center"><img src="https://github.com/burghoff/Scientific-Inkscape/blob/main/examples/Thinline_enhancement_portable.svg" alt="drawing" ></img></p>

### Embedded images
It is common for figures to have raster images embedded within, such as photographs, SEMs, Western blots, etc. However, much of the time the embedded images end up making file sizes that are *far* larger than necessary. This can happen if you take a high-resolution photo and clip it, or if you shrink a high resolution photo to make it a small inset, etc. There are papers with embedded photos that have an effective resolution of 10,000 DPI! Most of the time, it doesn't make sense to have a multi-MB TIFF embedded in your document. It was for this reason that the Embedded image resampling option of the Autoexporter was introduced, which resamples your rasters at a more reasonable resolution (typically 300 DPI). It can also embed them as a JPG for further file size reduction, although this should only be done for photos.

### Text
When embedding text, you should exercise some caution with respect to fonts. When generating PDFs, fonts are embedded and you do not have to worry. However, if you are making EMFs or Plain SVGs, you should be aware that the text may not appear exactly the same on all platforms, especially if you are using anything other than the most common fonts (Arial, Helvetica, Calibi, etc.). If you want to guarantee that your fonts look the same everywhere, you should use the "Convert text to paths" option of the Autoexporter. This is also recommended if you are giving a presentation on a computer that is not your own.
