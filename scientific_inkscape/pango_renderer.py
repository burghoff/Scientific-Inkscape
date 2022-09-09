#!/usr/bin/env python
# coding=utf-8
#
# Copyright (C) 2021 David Burghoff, dburghoff@nd.edu
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

# Some functions used for setting up a blank GTK window and rendering Pango text,
# for font metric calculation. Reuses the same layout for all rendering.

DEBUG_FONTS = True

# Try to import GTK 3 and make a window
import inkex
import dhelpers as dh
import os, warnings, sys, re

        
import fontconfig as fc
from fontconfig import FC


class PangoRenderer():
    def __init__(self):
        self.truefonts = dict();
        self.fontcharsets = dict();
        with warnings.catch_warnings():
            # Ignore ImportWarning for Gtk/Pango
            warnings.simplefilter('ignore') 
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                
                # GTk warning suppression from Martin Owens
                from gi.repository import GLib
                self.numlogs = 0;
                def _nope(*args, **kwargs): #
                    self.numlogs += 1;
                    return GLib.LogWriterOutput.HANDLED
                GLib.log_set_writer_func(_nope, None)
                
                from gi.repository import Pango
                from gi.repository import Gdk
                self.haspango = True;
            except:
                self.haspango = False;
                
            try:
                # requires some typelibs we do not have
                gi.require_version("PangoFT2", "1.0")
                from gi.repository import PangoFT2
                self.haspangoFT2 = True
            except:
                self.haspangoFT2 = False
    
        if self.haspango:
            self.disable_lcctype();
            if self.haspangoFT2:
                # dh.idebug('PangoFT2')
                self.ctx = Pango.Context.new();
                self.ctx.set_font_map(PangoFT2.FontMap.new());
            else:
                self.ctx = Gdk.pango_context_get();
            self.pangolayout = Pango.Layout(self.ctx)
            
            self.PANGO_VARIANTS = {
                'normal': Pango.Variant.NORMAL,
                'small-caps': Pango.Variant.SMALL_CAPS,
            }
            self.PANGO_STYLES = {
                'normal': Pango.Style.NORMAL,
                'italic': Pango.Style.ITALIC,
                'oblique': Pango.Style.OBLIQUE,
            }
            self.PANGO_WEIGHTS = {'thin':Pango.Weight.THIN,'ultralight':Pango.Weight.ULTRALIGHT,
                             'light':Pango.Weight.LIGHT,'semilight':Pango.Weight.SEMILIGHT,
                             'book':Pango.Weight.BOOK,'normal':Pango.Weight.NORMAL,
                             'medium':Pango.Weight.MEDIUM,'semibold':Pango.Weight.SEMIBOLD,
                             'bold':Pango.Weight.BOLD,'ultrabold':Pango.Weight.ULTRABOLD,
                             'heavy':Pango.Weight.HEAVY,'ultraheavy':Pango.Weight.ULTRAHEAVY,
                             '100':Pango.Weight.THIN,'200':Pango.Weight.ULTRALIGHT,
                             '300':Pango.Weight.LIGHT,'350':Pango.Weight.SEMILIGHT,
                             '380':Pango.Weight.BOOK,'400':Pango.Weight.NORMAL,
                             '500':Pango.Weight.MEDIUM,'600':Pango.Weight.SEMIBOLD,
                             '700':Pango.Weight.BOLD,'800':Pango.Weight.ULTRABOLD,
                             '900':Pango.Weight.HEAVY,'1000':Pango.Weight.ULTRAHEAVY}
            self.PANGO_STRETCHES = {'ultra-condensed':Pango.Stretch.ULTRA_CONDENSED,
                               'extra-condensed':Pango.Stretch.EXTRA_CONDENSED,
                               'condensed':Pango.Stretch.CONDENSED,
                               'semi-condensed':Pango.Stretch.SEMI_CONDENSED,
                               'normal':Pango.Stretch.NORMAL,
                               'semi-expanded':Pango.Stretch.SEMI_EXPANDED,
                               'expanded':Pango.Stretch.EXPANDED,
                               'extra-expanded':Pango.Stretch.EXTRA_EXPANDED,
                               'ultra-expanded':Pango.Stretch.ULTRA_EXPANDED}
            
            # Conversions from Pango to fontconfig
            self.PW_to_FCW = {Pango.Weight.THIN:FC.WEIGHT_THIN,Pango.Weight.ULTRALIGHT:FC.WEIGHT_ULTRALIGHT,Pango.Weight.ULTRALIGHT:FC.WEIGHT_EXTRALIGHT,
             Pango.Weight.LIGHT:FC.WEIGHT_LIGHT,Pango.Weight.SEMILIGHT:FC.WEIGHT_DEMILIGHT,Pango.Weight.SEMILIGHT:FC.WEIGHT_SEMILIGHT,
             Pango.Weight.BOOK:FC.WEIGHT_BOOK,Pango.Weight.NORMAL:FC.WEIGHT_REGULAR,Pango.Weight.NORMAL:FC.WEIGHT_NORMAL,
             Pango.Weight.MEDIUM:FC.WEIGHT_MEDIUM,Pango.Weight.SEMIBOLD:FC.WEIGHT_DEMIBOLD,Pango.Weight.SEMIBOLD:FC.WEIGHT_SEMIBOLD,
             Pango.Weight.BOLD:FC.WEIGHT_BOLD,Pango.Weight.ULTRABOLD:FC.WEIGHT_EXTRABOLD,Pango.Weight.ULTRABOLD:FC.WEIGHT_ULTRABOLD,
             Pango.Weight.HEAVY:FC.WEIGHT_BLACK,Pango.Weight.HEAVY:FC.WEIGHT_HEAVY,
             Pango.Weight.ULTRAHEAVY:FC.WEIGHT_EXTRABLACK,Pango.Weight.ULTRAHEAVY:FC.WEIGHT_ULTRABLACK}
            
            self.PS_to_FCS = {Pango.Style.NORMAL:FC.SLANT_ROMAN,Pango.Style.ITALIC:FC.SLANT_ITALIC,Pango.Style.OBLIQUE:FC.SLANT_OBLIQUE}

            self.PS_to_FCW = {Pango.Stretch.ULTRA_CONDENSED:FC.WIDTH_ULTRACONDENSED,Pango.Stretch.EXTRA_CONDENSED:FC.WIDTH_EXTRACONDENSED,
             Pango.Stretch.CONDENSED:FC.WIDTH_CONDENSED,Pango.Stretch.SEMI_CONDENSED:FC.WIDTH_SEMICONDENSED,
             Pango.Stretch.NORMAL:FC.WIDTH_NORMAL,Pango.Stretch.SEMI_EXPANDED:FC.WIDTH_SEMIEXPANDED,
             Pango.Stretch.EXPANDED:FC.WIDTH_EXPANDED,Pango.Stretch.EXTRA_EXPANDED:FC.WIDTH_EXTRAEXPANDED,
             Pango.Stretch.ULTRA_EXPANDED:FC.WIDTH_ULTRAEXPANDED}
            
            self.PANGOSIZE = 1000;  # size of text to render. 1000 is good
            self.pufd = Pango.units_from_double;
            self.putd = Pango.units_to_double;
        
            self.families = self.ctx.get_font_map().list_families()
            self.fmdict = {f.get_name(): [fc.get_face_name() for fc in f.list_faces()] for f in self.families}
            # self.fmdict2 = {f.get_name(): [(fc.describe().to_string(),fc.is_synthesized()) for fc in f.list_faces()] for f in self.families}
            # dh.idebug([f.get_name() for f in self.families])
            
            self.all_faces = [fc.describe().to_string() for fm in self.families for fc in fm.list_faces()];
            self.all_desc  = [fc.describe()             for fm in self.families for fc in fm.list_faces()];
            # dh.idebug(self.all_faces)

            
    
    # Search the /etc/fonts/conf.d folder for the default sans-serif font
    def Find_Default_Sanserifs(self):
        bloc = dh.Get_Binary_Loc();    
        
        import platform
        ikdir = os.path.dirname(os.path.dirname(os.path.abspath(bloc)))
        if platform.system().lower() == "darwin":
            confd = os.path.join(os.path.join(ikdir,'Resources','etc','fonts','conf.d'));
        elif platform.system().lower() == "windows":
            confd = os.path.join(os.path.join(ikdir,'etc','fonts','conf.d'));
        else:
            confd = os.path.join(os.path.join(ikdir,'etc','fonts','conf.d'));
        
        fns = [f.name for f in os.scandir(confd) if len(f.name)>1 and f.name[0:2] in [str(v) for v in range(60,70)]]
        fns = [os.path.join(confd,f) for f in fns];
        
        gfn = [fn for fn in fns if os.path.split(fn)[1]=='60-latin.conf'];
        if len(gfn)>0:
            fns = gfn  # use 60-latin.conf if it is available, otherwise find the first
        
        ssbackups = [];
        for fn in fns:
            from lxml import etree
            mytree = etree.parse(fn)
            myroot = mytree.getroot()
            
            for el in myroot.getchildren():
                if el.tag=='alias':
                    for el2 in el.getchildren():
                        if el2.tag=='family' and el2.text=='sans-serif':
                            nextel = next(el2.itersiblings());
                            if nextel.tag=='prefer':
                                for el3 in nextel.getchildren():
                                    if el3.tag=='family':
                                        ssbackups.append(el3.text)
            if len(ssbackups)>0:
                break
        return ssbackups
            
    
    def Set_Text_Style(self,stystr):
        sty2 = stystr.split(';');
        sty2 = {s.split(':')[0] : s.split(':')[1] for s in sty2}
        
        msty = ['font-family','font-weight','font-style','font-variant','font-stretch'] # mandatory style
        for m in msty:
            if m not in sty2:
                sty2[m]=dh.default_style_atts[m]
        # myfont = sty2['font-family'].replace('sans-serif',self.defaultfont)
        
        from gi.repository import Pango
        
        fd = Pango.FontDescription(sty2['font-family']);
        fd.set_weight( self.PANGO_WEIGHTS[  sty2['font-weight']])
        fd.set_variant(self.PANGO_VARIANTS[ sty2['font-variant']])
        fd.set_style(  self.PANGO_STYLES[   sty2['font-style']])
        fd.set_stretch(self.PANGO_STRETCHES[sty2['font-stretch']])
        fd.set_absolute_size(self.pufd(self.PANGOSIZE))
        
        logsbefore = self.numlogs;
        fnt = self.ctx.get_font_map().load_font(self.ctx,fd)
        success = self.numlogs==logsbefore and fnt is not None
        
        # if not(success):
        #     # Occasionally valid fonts are not matched by Pango. When this happens,
        #     # find the face full name using fontconfig and try to match it to
        #     # the faces found by Pango
        #     # This should work, but is sometimes not great due to Pango limitations. 
        #     pat = fc.Pattern.create(vals = (
        #             (fc.PROP.FAMILY, sty2['font-family']),
        #             (fc.PROP.WIDTH,  self.PS_to_FCW[self.PANGO_STRETCHES[sty2['font-stretch']]]),
        #             (fc.PROP.WEIGHT, self.PW_to_FCW[self.PANGO_WEIGHTS[  sty2['font-weight']]]),
        #             (fc.PROP.SLANT,  self.PS_to_FCS[self.PANGO_STYLES[   sty2['font-style']]])   ))
        #     conf = fc.Config.get_current()
        #     conf.substitute(pat, FC.MatchPattern)
        #     pat.default_substitute()
        #     found,status = conf.font_match(pat)
        #     fullname = found.get(fc.PROP.FULLNAME,0)[0];
            
        #     # Find Pango faces that have all of the same words as the fc name
        #     def wlist(x):
        #         return x.replace(',','').split(' ')
        #     matches = [ff for ff in self.all_faces if all([w in \
        #                 wlist(ff) for w in wlist(fullname)])];
        #     if len(matches)>0:
        #         ls = [len(ff) for ff in matches];
        #         mini = ls.index(min(ls)) # pick the shortest match
        #         fd = self.all_desc[self.all_faces.index(matches[mini])]
            
        #         oldstr = fd.to_string();
        #         # fd = Pango.FontDescription(matches[mini]);
        #         fd = self.all_desc[self.all_faces.index(matches[mini])]
        #         fd.set_absolute_size(self.pufd(self.PANGOSIZE))
        #         newstr = fd.to_string()
                
        #         logsbefore = self.numlogs;
        #         fnt = self.ctx.get_font_map().load_font(self.ctx,fd)
        #         success = self.numlogs==logsbefore and newstr!=oldstr and fnt is not None
        #         dh.idebug((oldstr,newstr,success))
                
            
        self.pangolayout.set_font_description(fd);
        if success:
            fm = fnt.get_metrics();
            fm = [self.putd(v)/self.PANGOSIZE for v in [fm.get_height(),fm.get_ascent(),fm.get_descent()]]
            return success, fm
        else:
            return success, None
        
        
    def Render_Text(self,texttorender):
        self.pangolayout.set_text(texttorender,-1)
        
        
    # Scale extents and return extents as standard bboxes (0:logical, 1:ink,
    # 2: ink relative to anchor/baseline)
    def process_extents(self,ext,ascent):
        lr = ext.logical_rect;
        lr = [self.putd(v)/self.PANGOSIZE for v in [lr.x,lr.y,lr.width,lr.height]];
        ir = ext.ink_rect;
        ir = [self.putd(v)/self.PANGOSIZE for v in [ir.x,ir.y,ir.width,ir.height]];
        
        ir_rel = [ir[0] - lr[0], ir[1] - lr[1] - ascent, ir[2], ir[3]]
        return lr, ir, ir_rel
              
        
    def Get_Character_Extents(self,ascent):
        # Iterate through the layout to get the logical width of each character
        # If there is differential kerning applied, it is applied to the 
        # width of the first character. For example, the 'V' in 'Voltage'
        # will be thinner due to the 'o' that follows.
        # Units: relative to font size
        loi = self.pangolayout.get_iter();
        ws=[];
        ce = loi.get_cluster_extents();
        ws.append(self.process_extents(ce,ascent));
        moved = loi.next_char();
        while moved:
            ce = loi.get_cluster_extents();
            ws.append(self.process_extents(ce,ascent));
            moved = loi.next_char();
            
        numunknown = self.pangolayout.get_unknown_glyphs_count()
        return ws, numunknown

    
    def disable_lcctype(self):
        self.lcctype = os.environ.get('LC_CTYPE');
        if self.lcctype is not None and sys.platform=='darwin':
            del os.environ['LC_CTYPE'] # suppress Mac warning
    def enable_lcctype(self):
        if self.lcctype is not None and sys.platform=='darwin':
            os.environ['LC_CTYPE'] = self.lcctype;
    
    # Use fontconfig to get the true font that most text will be rendered as
    # Should work in all post-1.0 versions
    def get_true_font(self,nominalfont):
        if nominalfont not in self.truefonts:
            # self.disable_lcctype();
           
            ff_strip = nominalfont.replace("'",'').replace('"','')
            pat = fc.Pattern.name_parse(re.escape(ff_strip))
            conf = fc.Config.get_current()
            conf.substitute(pat, FC.MatchPattern)
            pat.default_substitute()
            found,status = conf.font_match(pat)
            
            # self.enable_lcctype();
            
            self.truefonts[nominalfont]    = found.get(fc.PROP.FAMILY,0)[0]
            self.fontcharsets[found.get(fc.PROP.FAMILY,0)[0]] = found.get(fc.PROP.CHARSET,0)[0]
        return self.truefonts[nominalfont]
    
    
    # Get the true font by character (in case characters are missing)
    def get_true_font_by_char(self,nominalfont,chars):
        if nominalfont in self.truefonts:
            fam = self.truefonts[nominalfont]
            d = {k:fam for k in chars if ord(k) in self.fontcharsets[fam]}
        else:
            d = {};
        
        if len(d)<len(chars):
            # self.disable_lcctype();
            pat = fc.Pattern.name_parse(nominalfont)
            conf = fc.Config.get_current()
            conf.substitute(pat, FC.MatchPattern)
            pat.default_substitute()
        
            found, total_coverage, status = conf.font_sort(pat, trim = True, want_coverage = False)
            
            for f in found:
                fam = f.get(fc.PROP.FAMILY,0)[0];
                cs = f.get(fc.PROP.CHARSET,0)[0];
                self.fontcharsets[fam] = cs;
                d2 = {k:fam for k in chars if ord(k) in cs and k not in d}
                d.update(d2);
                if len(d)==len(chars):
                    break;
            # self.enable_lcctype();
        return d
    
# For testing purposes    
def Unicode_Test_Doc():
    rng = range(1,10000)
    HGT = 256;
    WDH =(max(rng)-(max(rng)%HGT))/HGT+1
    SIZE = 1;
    doch = (HGT+1)*SIZE
    docw = WDH*SIZE
    
    svgstart = '<svg width="'+str(docw)+'mm" height="'+str(doch)+'mm" viewBox="0 0 '+str(docw)+' '+str(doch)+'" id="svg60386" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg"> <defs id="defs60383" />'
    svgstop = "</svg>"
    txt1 = '<text xml:space="preserve" style="'
    txt2 = '" id="text'
    txt3 = '" y="'
    txt4 = '" x="'
    txt5 = '">'
    txt6 = "</text>"
    svgtexts = ""
    import tempfile, os
    f = tempfile.NamedTemporaryFile(mode="wb",delete=False,suffix='.svg')
    tmpname = os.path.abspath(f.name);
    f.write(svgstart.encode("utf8"))
    from xml.sax.saxutils import escape

    cnt = 0;
    for ii in rng:
        cnt+=1;
        c=chr(ii)
        sty = 'font-size:'+str(SIZE)+'px'
        x = str((ii-(ii%HGT))/HGT*SIZE)+'px'
        y = str((ii%HGT+1)*SIZE)+'px'
        svgtexts += txt1 + sty + txt2 + str(cnt) + txt3 + y + txt4 + x + txt5 + escape(c) + txt6
        if cnt % 1000 == 0:
            f.write(svgtexts.encode("utf8"))
            svgtexts = ""

    f.write((svgtexts + svgstop).encode("utf8"))
    f.close()
    
    def overwrite_output(filein,fileout):      
        try:
            os.remove(fileout)
        except:
            pass
        arg2 = [
            dh.Get_Binary_Loc(),
            "--export-background",
            "#ffffff",
            "--export-background-opacity",
            "1.0",
            "--export-filename",
            fileout,
            filein,
        ]
        dh.subprocess_repeat(arg2)
    
    tmp2 = tmpname.replace('.svg','.pdf');
    tmp3 = tmpname.replace('.svg','_2.svg')
    
    overwrite_output(tmpname,tmp2);
    overwrite_output(tmp2,tmp3);
    svg2 = inkex.load_svg(tmp3).getroot();
    
def Pango_Test():
    # For testing Gtk-based Pango rendering, modified from
    # https://web.archive.org/web/20180615145907/http://jcoppens.com/soft/howto/pygtk/pangocairo.en.php
    # Uses PangoCairo to output to a png
    # Only works in Inkscape v1.1
    from gi.repository import Pango
    from gi.repository import PangoCairo as pc
    import cairo
    
    RADIUS = 500
    FONT = "Bahnschrift Light Condensed, "+str(RADIUS/5)
    filename = 'Pango test.png'

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2 * RADIUS, int(RADIUS/2))
    cairo_ctx = cairo.Context(surface)

    cairo_ctx.set_source_rgb(1.0, 1.0, 1.0)
    cairo_ctx.paint()
    
    cairo_ctx.translate(RADIUS, 0)
    pc_ctx = pc.create_context(cairo_ctx)
    pc_layout = pc.create_layout(cairo_ctx)

    desc = Pango.FontDescription(FONT)
    # desc.set_stretch(Pango.Stretch.CONDENSED)
    # desc.set_weight(Pango.Weight.LIGHT)
 
    
    markup = 'Test 123 <span font-family="Cambria Math">⎣</span>'
    pm = Pango.parse_markup(markup, -1, '\x00')
    pc_layout.set_attributes(pm[1])
    pc_layout.set_text(pm[2])
    
    pc_layout.set_font_description(desc)

    cairo_ctx.save()
    cairo_ctx.set_source_rgb(0, 0, 0);
    pc.update_layout(cairo_ctx,pc_layout)

    width, height = pc_layout.get_size()
    cairo_ctx.move_to(-(float(width) / Pango.SCALE) / 2, 0)
    pc.show_layout(cairo_ctx,pc_layout)

    cairo_ctx.restore()
    success = surface.write_to_png(filename)
    
    fnt = pc_ctx.get_font_map().load_font(pc_ctx,desc)
    fntset = pc_ctx.get_font_map().load_fontset(pc_ctx,desc,Pango.Language.get_default())
    # dh.idebug(fntset.get_font(ord('⎣')).describe().to_string())
    
    from gi.repository import Gdk
    fm2 = Gdk.pango_context_get().get_font_map().list_families();
    all_faces = [fc.describe().to_string() for fm in fm2 for fc in fm.list_faces()];
    
    
    families = pc_ctx.get_font_map().list_families()
    fmdict = {f.get_name(): [fc.get_face_name() for fc in f.list_faces()] for f in families}
    
