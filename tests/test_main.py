# coding=utf-8

STORE_REFS = False
fname = 'Other_tests.svg'
fname2 = 'Other_tests_nonuniform.svg'
aename = 'Autoexporter_tests.svg'

MAXPAPERS = 0
flattentext = 'Text_tests.svg'
flattenrest = 'Acid_tests.svg';
priority_flatten = ['']
exclude_flatten = ['Ohtani_SA_2019_Deep_group.svg',flattentext,flattenrest,fname,aename]

flattenerargs = ("--id=layer1","--testmode=True")
aeargs = ("--testmode=True",)

version = '1.2.1'
lprofile = False

testflattentext,testflattenrest,testflattenpapers,testscalecorrection,testscalecorrection2,\
testscalematching,testscalefixed,testghoster,testcbc,testfm,testhomogenizer,testhomogenizer2, testae = (False,)*13

testflattentext     = True;
testflattenrest     = True; 
testflattenpapers   = True; 
testscalecorrection = True;
testscalecorrection2= True;
testscalematching   = True;
testscalefixed      = True;
testghoster         = True;
testcbc             = True;
testfm              = True;
testhomogenizer     = True;
testhomogenizer2    = True;
testae              = True;

# import importlib.util
# spec = importlib.util.spec_from_file_location("module.name", "/path/to/file.py")
# foo = importlib.util.module_from_spec(spec)
# spec.loader.exec_module(foo)
# foo.MyClass()

vpaths = {'1.0' :  ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python38.zip', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8\\lib-dynload', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8\\site-packages', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']+\
                   ['D:\\Inkscapes\\inkscape-1.0.2-2-x64\\bin'],
          '1.1' :  ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python39.zip', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9\\site-packages', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']+\
                   ['D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\bin'],
          '1.2' :  ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\lib\\python39.zip', 'D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\lib\\python3.9', 'D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\lib\\python3.9\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\lib\\python3.9\\site-packages', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']+\
                   ['D:\\Inkscapes\\inkscape-1.2_2022-05-15_dc2aedaf03-x64\\bin'],
          '1.2.1': ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\lib\\python310.zip', 'D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\lib\\python3.10', 'D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\lib\\python3.10\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\lib\\python3.10\\site-packages', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']+\
                   ['D:\\Inkscapes\\inkscape-1.2.1_2022-07-14_9c6d41e410-x64\\bin'],
          '1.3': ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\lib\\python310.zip', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\lib\\python3.10', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\lib\\python3.10\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\lib\\python3.10\\site-packages', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'D:\\Inkscapes\\inkscape-1.3-dev_2022-07-25_5e015900-x64\\bin']}

if version=='1.0':
    flattenerargs += ("--v=1.0",)
    aeargs += ("--v=1.0",)
elif version == '1.1':
    aeargs += ("--v=1.1",)

import sys; sys.path += vpaths[version]
import os; os.environ['LINEPROFILE'] = str(lprofile)

from flatten_plots import FlattenPlots
from scale_plots import ScalePlots
from text_ghoster import TextGhoster
from combine_by_color import CombineByColor
from favorite_markers import FavoriteMarkers
from homogenizer import Homogenizer
from autoexporter import AutoExporter
from inkex.tester import ComparisonMixin, TestCase
from inkex.tester.filters import CompareWithoutIds
from inkex.tester.filters import Compare 

import os,re
def get_files(dirin):
    fs = []
    for f in os.scandir(dirin):
        if f.name[-4:]=='.svg':
            fs.append(os.path.join(os.path.abspath(dirin),f.name))
    return fs
class CompareNeg0(Compare):
    """Convert negative 0s into regular 0s"""
    @staticmethod
    def filter(contents):
        c2 = re.sub(rb'-0 ', b"0 ", contents)
        # c3 = re.sub(rb'-0)', b"0)", c2)
        c3 = c2.replace(b'-0)',b'0)')
        c4 = re.sub(rb'-0,', b"0,", c3)
        return c4
class CompareDx0(Compare):
    """Remove empty dx/dy values"""
    @staticmethod
    def filter(contents):
        c2 = re.sub(rb'dx="0"', b"", contents)
        c3 = re.sub(rb'dy="0"', b"", c2)
        return c3
    
class CompareTransforms(Compare):
    """Standardize commas in transforms"""
    @staticmethod
    def filter(contents):
        mmat = [];
        for tr in [rb'matrix',rb'scale',rb'translate']:
            mmat += [m.span()[1] for m in re.compile(tr+rb'\(').finditer(contents)]
        pmat = [m.span()[0] for m in re.compile(rb'\)').finditer(contents)]
        repl = [];
        for m in reversed(mmat):
            myp = min([pl for pl in pmat if pl>=m])
            newmat = re.sub(rb', ', rb" ", contents[m:myp])
            newmat = re.sub(rb',' , rb" ", newmat)
            repl.append((m,myp,newmat))
            
        def Make_Replacements(x,rs):
            rs = sorted(rs, key=lambda r: r[0])   
            if len(rs)>0:
                lst = 0; pieces=[]
                for r in rs:
                    pieces.append(x[lst:r[0]])
                    pieces.append(r[2])
                    lst = r[1]
                pieces.append(x[lst:])
                ret = b''.join(pieces)
            else:
                ret = x
            return ret
        ret = Make_Replacements(contents,repl)
        
        ret = re.sub(rb"scale\(0 0\)", rb"scale(0)", ret)
        ret = re.sub(rb'transform="translate\(0 0\)"', rb"", ret)
        return ret
    

# Go through the document and replace all ids contained in urls, in the
# order they appear in the document
class CompareURLs(Compare):
    @staticmethod
    def filter(contents):
        # print(contents)
        myid = b'SItestURL'
        def findurl(x):
            # Gets the first url#( ... ) content
            m = re.findall(rb"url\(\#(.*?)\)",x)
            g = [mv for mv in m if myid not in mv]  # exclude already substituted
            if len(g)==0:
                return None
            else:
                return g[0]
        
        f = findurl(contents)
        n = 0;
        while f is not None:
            newid = myid+(b"%.0f" % n);
            # print((f,newid))
            contents = re.sub(rb'"'      +f+rb'"',  rb'"'     +newid+rb'"',contents)
            contents = re.sub(rb'url\(\#'+f+rb'\)',rb'url\(\#'+newid+rb'\)',contents)
            n += 1
            f = findurl(contents)
        return contents
    
class CompareNumericFuzzy2(Compare):
    """
    Turn all numbers into shorter standard formats
    """
    @staticmethod
    def filter(contents):
        # def func(x):
        #     if b'matrix' in x:
        #         c2 = contents.strip(b'matrix(').strip(b')').split(b' ')
        #         c3 = b' '.join([b"%.3f" % (float(cv.group(0))) for cv in c2])
        #         return b'matrix('+c3+b')'
        #     else:
        #         return b"%.3f" % (float(x.group(0)))
            
        if version=='1.2':
            func = lambda m: b"%.3f" % (float(m.group(0)))
        else:
            func = lambda m: b"%.0f" % (float(m.group(0)))
        contents = re.sub(rb"\d+\.\d+(e[+-]\d+)?", func, contents)
        contents = re.sub(rb"(\d\.\d+?)0+\b", rb"\1", contents)
        contents = re.sub(rb"(\d)\.0+(?=\D|\b)", rb"\1", contents)
        return contents

if testflattentext:
    class TestFlattenerText(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        comparisons = [flattenerargs]
        compare_file = ['svg/'+flattentext]

if testflattenrest:
    class TestFlattenerRest(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        comparisons = [flattenerargs]
        compare_file = ['svg/'+flattenrest]
    
if testflattenpapers:
    class TestFlattenerPapers(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        comparisons = [flattenerargs]
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
    
if testscalecorrection:
    class TestScaleCorrection(ComparisonMixin, TestCase):  
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=g5224","--tab=correction")
        ]
if testscalecorrection2:
    class TestScaleCorrection2(ComparisonMixin, TestCase):  
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname2]
        comparisons = [
            ("--id=g109153","--id=g109019","--tab=correction")
        ]

if testscalematching:
    class TestScaleMatching(ComparisonMixin, TestCase):
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=rect5248","--id=g4982","--tab=matching")
        ]
if testscalefixed:
    class TestScaleFixed(ComparisonMixin, TestCase):
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=g4982","--tab=scaling",'--hscale=120','--vscale=80')
        ]
    
if testghoster:
    class TestGhoster(ComparisonMixin, TestCase):
        effect_class = TextGhoster
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=text28136",)
        ]
  
if testcbc:
    class TestCBC(ComparisonMixin, TestCase):
        effect_class = CombineByColor
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=layer1",)
        ]
    
if testfm:
    class TestFM(ComparisonMixin, TestCase):
        effect_class = FavoriteMarkers
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=path6928","--id=path6952","--smarker=True","--tab=markers")
        ]

if testhomogenizer:
    class TestHomogenizer(ComparisonMixin, TestCase):
        effect_class = Homogenizer
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=layer1","--fontsize=7","--setfontsize=True","--fixtextdistortion=True","--fontmodes=2", \
              "--setfontfamily=True","--fontfamily=Avenir",\
              "--setstroke=True","--setstrokew=0.75","--strokemodes=2","--fusetransforms=True")
        ]

if testhomogenizer2:
    class TestHomogenizer2(ComparisonMixin, TestCase):
        effect_class = Homogenizer
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds()]
        compare_file = ['svg/'+fname2]
        comparisons = [
            ("--id=layer1","--fontsize=7","--setfontsize=True","--fixtextdistortion=True","--fontmodes=2", \
              "--setfontfamily=True","--fontfamily=Avenir",\
              "--setstroke=True","--setstrokew=0.75","--strokemodes=2","--fusetransforms=True")
        ] 

if testae:
    class TestAutoExporter(ComparisonMixin, TestCase):
        effect_class = AutoExporter
        compare_filters = [CompareNumericFuzzy2(),CompareNeg0(),CompareDx0(),CompareTransforms(),CompareWithoutIds(),CompareURLs()]
        compare_file = ['svg/'+aename]
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