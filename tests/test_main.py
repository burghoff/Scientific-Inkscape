# coding=utf-8
STORE_REFS = False
fname = 'Other_tests.svg'

MAXPAPERS = 0
flattentext = 'Text_tests.svg'
flattenrest = 'Acid_tests.svg';
priority_flatten = ['Kazakov_2022_Illustrator_a.svg']
exclude_flatten = ['Ohtani_SA_2019_Deep_group.svg',flattentext,flattenrest,fname]

flattenerargs = [("--id=layer1","--testmode=True")]
aeargs = ("--testmode=True",)

import sys
# sys.path += ['C:\\Program Files\\Inkscape\\bin\\python39.zip', 'C:\\Program Files\\Inkscape\\bin', 'C:\\Program Files\\Inkscape\\share\\inkscape\\extensions', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape', 'C:\\Users\\burgh\\AppData\\Roaming\\Python\\Python39\\site-packages', 'C:\\Program Files\\Inkscape\\bin\\lib\\site-packages', 'C:\\Program Files\\Inkscape\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape']

version = '1.0'

if version=='1.0':
    sys.path += ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python38.zip', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8\\lib-dynload', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8\\site-packages', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']
    sys.path += ['D:\\Inkscapes\\inkscape-1.0.2-2-x64\\bin']
    flattenerargs[0] += ("--v=1.0",)
    aeargs += ("--v=1.0",)
elif version == '1.1':
    sys.path += ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python39.zip', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9\\site-packages', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']
    sys.path += ['D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\bin']
    aeargs += ("--v=1.1",)
else:
    sys.path += ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\lib\\python39.zip', 'D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\lib\\python3.9', 'D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\lib\\python3.9\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\lib\\python3.9\\site-packages', 'D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']
    sys.path += ['D:\\Inkscapes\\inkscape-1.2-beta_2022-04-05_1b65182ce9-x64\\bin']


from flatten_plots import FlattenPlots
from scale_plots import ScalePlots
from text_ghoster import TextGhoster
from combine_by_color import CombineByColor
from favorite_markers import FavoriteMarkers
from homogenizer import Homogenizer
from autoexporter import AutoExporter
from inkex.tester import ComparisonMixin, TestCase
from inkex.tester.filters import CompareWithoutIds,CompareNumericFuzzy
from inkex.tester.filters import Compare 

# print(flattenerargs)

import os
def get_files(dirin):
    fs = []
    for f in os.scandir(dirin):
        if f.name[-4:]=='.svg':
            fs.append(os.path.join(os.path.abspath(dirin),f.name))
    return fs

import re
class CompareNeg0(Compare):
    """Convert negative 0s into regular 0s"""
    @staticmethod
    def filter(contents):
        c2 = re.sub(rb'-0 ', b"0 ", contents)
        return c2
class CompareDx0(Compare):
    """Remove empty dx/dy values"""
    @staticmethod
    def filter(contents):
        c2 = re.sub(rb'dx="0"', b"", contents)
        c3 = re.sub(rb'dy="0"', b"", c2)
        return c3
class CompareNumericFuzzy2(Compare):
    """
    Turn all numbers into shorter standard formats

    1.2345678 -> 1.2346
    1.2300 -> 1.23, 50.0000 -> 50.0
    50.0 -> 50
    """
    # NUM_DIGITS = 1;
    @staticmethod
    def filter(contents):
        func = lambda m: b"%.3f" % (float(m.group(0)))
        contents = re.sub(rb"\d+\.\d+(e[+-]\d+)?", func, contents)
        contents = re.sub(rb"(\d\.\d+?)0+\b", rb"\1", contents)
        contents = re.sub(rb"(\d)\.0+(?=\D|\b)", rb"\1", contents)
        return contents
    
 
class TestFlattenerText(ComparisonMixin, TestCase):
    effect_class = FlattenPlots
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    comparisons = flattenerargs
    compare_file = ['svg/'+flattentext]
    

class TestFlattenerRest(ComparisonMixin, TestCase):
    effect_class = FlattenPlots
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    comparisons = flattenerargs
    compare_file = ['svg/'+flattenrest]
    

class TestFlattenerPapers(ComparisonMixin, TestCase):
    effect_class = FlattenPlots
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    comparisons = flattenerargs
    allfs = get_files(os.getcwd()+'/data/svg');
    badfs = [v for v in allfs if any([es in v for es in exclude_flatten])];
    for b in badfs:
        allfs.remove(b)
    fonly = [os.path.split(f)[1] for f in allfs];
    for p in reversed(priority_flatten):
        if p in fonly:
            myi = fonly.index(p);
            myv = allfs[myi];
            allfs.remove(myv);
            allfs=[myv]+allfs
            myv = fonly[myi];
            fonly.remove(myv);
            fonly=[myv]+fonly
    compare_file = []
    for f in allfs:
        spl=os.path.split(f);
        compare_file.append('svg/'+spl[1])
    compare_file = compare_file[0:MAXPAPERS]
    

class TestScaleCorrection(ComparisonMixin, TestCase):  
    effect_class = ScalePlots
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        ("--id=g5224","--tab=correction")
    ]

class TestScaleMatching(ComparisonMixin, TestCase):
    effect_class = ScalePlots
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        ("--id=rect5248","--id=g4982","--tab=matching")
    ]
class TestScaleFixed(ComparisonMixin, TestCase):
    effect_class = ScalePlots
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        ("--id=g4982","--tab=scaling",'--hscale=120','--vscale=80')
    ]
    
    
class TestGhoster(ComparisonMixin, TestCase):
    effect_class = TextGhoster
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        ("--id=text28136",)
    ]
    
class TestCBC(ComparisonMixin, TestCase):
    effect_class = CombineByColor
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        ("--id=layer1",)
    ]
    

class TestFM(ComparisonMixin, TestCase):
    effect_class = FavoriteMarkers
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        ("--id=path6928","--id=path6952","--smarker=True","--tab=markers")
    ]


class TestHomogenizer(ComparisonMixin, TestCase):
    effect_class = Homogenizer
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        ("--id=layer1","--fontsize=7","--setfontsize=True","--fixtextdistortion=True","--fontmodes=2", \
          "--setfontfamily=True","--fontfamily=Avenir",\
          "--setstroke=True","--setstrokew=0.75","--strokemodes=2","--fusetransforms=True")
    ]     
    
class TestAutoExporter(ComparisonMixin, TestCase):
    effect_class = AutoExporter
    compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareWithoutIds()]
    compare_file = ['svg/'+fname]
    comparisons = [
        aeargs
    ]    




if __name__ == "__main__":
    import sys, inspect
    for name, obj in inspect.getmembers(sys.modules[__name__]):
        if inspect.isclass(obj) and issubclass(obj, (ComparisonMixin)) and issubclass(obj, (TestCase)):
            fs = obj.compare_file
            cs = obj.comparisons
            for f in fs:
                for c in cs:
                    fpath = os.path.abspath('data/'+f);
                    args = list(c)+[fpath]
                    
                    try:
                        cmpfile = os.path.split(obj().get_compare_cmpfile(list(c) + [str(f)[4:]]))[1]
                    except:
                        # cmpfile = os.path.split(obj().get_compare_outfile(list(c) + [str(f)[4:]]))[1]
                        # Modified get_compare_outfile from v1.0 and 1.1
                        import hashlib
                        myobj = obj();
                        myargs = list(c) + [str(f)[4:]];
                       
                        opstr = '__'.join(myargs)\
                                    .replace(myobj.tempdir, 'TMP_DIR')\
                                    .replace(myobj.datadir(), 'DAT_DIR')
                        opstr = re.sub(r'[^\w-]', '__', opstr)
                        if opstr:
                            if len(opstr) > 127:
                                # avoid filename-too-long error
                                opstr = hashlib.md5(opstr.encode('latin1')).hexdigest()
                            opstr = '__' + opstr
                        cmpfile = os.path.split(f"{myobj.effect_name}{opstr}.out")[1] 
                        
                    
                    pout = 'data/refs/'+cmpfile
                    pout2 = 'data/svg/outputs/'+cmpfile.replace('.out','.svg')
                    fout = os.path.abspath(pout2)
                    print(pout2)
                    obj.effect_class().run(args,fout);
                    
                    if STORE_REFS:
                        import shutil
                        shutil.copyfile(os.path.abspath(pout2),os.path.abspath(pout))
                        print(pout)
    # dh.write_debug()