# coding=utf-8

STORE_REFS = False
fname = 'Other_tests.svg'
fname2 = 'Other_tests_nonuniform.svg'
aename = 'Autoexporter_tests.svg'
aepages = 'Multipage_nonuniform.svg'

MAXPAPERS = 0
flattentext = 'Text_tests.svg'
flattenrest = 'Acid_tests.svg';
priority_flatten = ['']
exclude_flatten = ['Ohtani_SA_2019_Deep_group.svg',flattentext,flattenrest,fname,aename]

flattenerargs = ("--id=layer1","--testmode=True")
aeargs = ("--testmode=True",)

version = '1.2'
usepango = False
lprofile = False

testflattentext,testflattenrest,testflattenpapers,testscalecorrection,testscalecorrection2,\
testscalematching,testscalefixed,testghoster,testcbc,testfm,testhomogenizer,testhomogenizer2, testae,testaemp = (False,)*14

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
testaemp            = True;



vpaths = {'1.0' :  ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python38.zip', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8\\lib-dynload', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\lib\\python3.8\\site-packages', 'D:\\Inkscapes\\inkscape-1.0.2-2-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']+\
                   ['D:\\Inkscapes\\inkscape-1.0.2-2-x64\\bin'],
          '1.1' :  ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python39.zip', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\lib\\python3.9\\site-packages', 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal']+\
                   ['D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64\\bin'],
          '1.2': ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\lib\\python310.zip', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\lib\\python3.10', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\lib\\python3.10\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\lib\\python3.10\\site-packages', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'G:\\My Drive\\Work\\2021.03 Inkscape extension\\personal', 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-01_b0a8486541-x64\\bin'],
          '1.3': ['C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\share\\inkscape\\extensions', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\lib\\python310.zip', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\lib\\python3.10', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\lib\\python3.10\\lib-dynload', 'C:\\Users\\burgh\\AppData\\Roaming\\inkscape\\extensions\\personal', 'C:\\Users\\burgh\\.local\\lib\\python3.10-mingw_x86_64\\site-packages', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\lib\\python3.10\\site-packages', 'G:\\My Drive\\Work\\Inkscape extension\\personal', 'G:\\My Drive\\Storage\\Github\\Academic-Inkscape\\scientific_inkscape', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\share\\inkscape\\extensions\\inkex\\deprecated-simple', 'G:\\My Drive\\Work\\Inkscape extension\\personal', 'G:\\My Drive\\Work\\Inkscape extension\\personal', 'D:\\Inkscapes\\inkscape-1.3-dev_2023-03-12_4435d25a6-x64\\bin']};
    
import os
if 'TESTMAINVERSION' in os.environ:
    version = os.environ['TESTMAINVERSION']
if version=='1.0':
    flattenerargs += ("--v=1.0",)

import sys; sys.path += vpaths[version]
os.environ['LINEPROFILE'] = str(lprofile)
os.environ['USEPANGO']=str(usepango)


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
# class CompareNeg0(Compare):
#     """Convert negative 0s into regular 0s"""
#     @staticmethod
#     def filter(contents):
        # c2 = re.sub(rb'-0 ', b"0 ", contents)
        # c3 = c2.replace(b'-0)',b'0)')
        # c4 = re.sub(rb'-0,', b"0,", c3)
        # return c4
        # return contents
# class CompareDx0(Compare):
#     """Remove empty dx/dy values"""
#     @staticmethod
#     def filter(contents):
#         c2 = re.sub(rb'dx="0"', b"", contents)
#         c3 = re.sub(rb'dy="0"', b"", c2)
#         return c3
    
# class CompareTransforms(Compare):
#     """Standardize commas in transforms"""
#     @staticmethod
#     def filter(contents):
        # mmat = [];
        # for tr in [rb'matrix',rb'scale',rb'translate']:
        #     mmat += [m.span()[1] for m in re.compile(tr+rb'\(').finditer(contents)]
        # pmat = [m.span()[0] for m in re.compile(rb'\)').finditer(contents)]
        # repl = [];
        # for m in reversed(mmat):
        #     myp = min([pl for pl in pmat if pl>=m])
        #     newmat = re.sub(rb', ', rb" ", contents[m:myp])
        #     newmat = re.sub(rb',' , rb" ", newmat)
        #     repl.append((m,myp,newmat))
            
        # def Make_Replacements(x,rs):
        #     rs = sorted(rs, key=lambda r: r[0])   
        #     if len(rs)>0:
        #         lst = 0; pieces=[]
        #         for r in rs:
        #             pieces.append(x[lst:r[0]])
        #             pieces.append(r[2])
        #             lst = r[1]
        #         pieces.append(x[lst:])
        #         ret = b''.join(pieces)
        #     else:
        #         ret = x
        #     return ret
        # ret = Make_Replacements(contents,repl)
        # ret = re.sub(rb"scale\(0 0\)", rb"scale(0)", ret)
        # ret = re.sub(rb'transform="translate\(0 0\)"', rb"", ret)
        # return ret
        # return contents
    

# Replace all ids contained in urls in the order they appear in the document
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
            contents = re.sub(rb'"'      +f+rb'"',  rb'"'     +newid+rb'"',contents)
            contents = re.sub(rb'url\(\#'+f+rb'\)',rb'url\(\#'+newid+rb'\)',contents)
            n += 1
            f = findurl(contents)
        return contents
    
import math    
def matrix_multiply(a, b):
    # Initialize result matrix
    result = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    # Multiply the matrices
    for i in range(3):
        for j in range(3):
            for k in range(3):
                result[i][j] += a[i][k] * b[k][j]
    return result

# Converts a transform string into a standard matrix
def transform_to_matrix(transform):
    # Regular expression pattern to match transform functions
    pattern = rb'\b(scale|translate|rotate|skewX|skewY|matrix)\(([^\)]*)\)'
    # Initialize result matrix
    
    null   = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    matrix = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    if b'none' in transform or not re.search(pattern, transform):
        return null
    # Find all transform functions
    for match in re.finditer(pattern, transform):
        transform_type = match.group(1)
        transform_args = list(map(float, re.split(rb'[\s,]+', match.group(2))))

        if transform_type == b'scale':
            # Scale transform
            if len(transform_args) == 1:
                sx = sy = transform_args[0]
            elif len(transform_args) == 2:
                sx, sy = transform_args
            else:
                return null
            matrix = matrix_multiply(matrix, [[sx, 0, 0], [0, sy, 0], [0, 0, 1]])
        elif transform_type == b'translate':
            # Translation transform
            if len(transform_args) == 1:
                tx = transform_args[0]; ty = 0;
            elif len(transform_args) == 2:
                tx, ty = transform_args
            else:
                return null
            matrix = matrix_multiply(matrix, [[1, 0, tx], [0, 1, ty], [0, 0, 1]])
        elif transform_type == b'rotate':
            # Rotation transform
            if len(transform_args) == 1:
                angle = transform_args[0]
                cx = cy = 0
            elif len(transform_args) == 3:
                angle, cx, cy = transform_args
            else:
                return null
            angle = angle * math.pi / 180  # Convert angle to radians
            matrix = matrix_multiply(matrix, [[1, 0, cx], [0, 1, cy], [0, 0, 1]])
            matrix = matrix_multiply(matrix, [[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]])
            matrix = matrix_multiply(matrix, [[1, 0, -cx], [0, 1, -cy], [0, 0, 1]])
        elif transform_type == b'skewX':
            # SkewX transform
            if len(transform_args) == 1:
                angle = transform_args[0]
            else:
                return null
            angle = angle * math.pi / 180  # Convert angle to radians
            matrix = matrix_multiply(matrix, [[1, math.tan(angle), 0], [0, 1, 0], [0, 0, 1]])
        elif transform_type == b'skewY':
            # SkewY transform
            if len(transform_args) == 1:
                angle = transform_args[0]
            else:
                return null
            angle = angle * math.pi / 180  # Convert angle to radians
            matrix = matrix_multiply(matrix, [[1, 0, 0], [math.tan(angle), 1, 0], [0, 0, 1]])
        elif transform_type == b'matrix':
            # Matrix transform
            if len(transform_args) == 6:
                a, b, c, d, e, f = transform_args
            else:
                return null
            matrix = matrix_multiply(matrix, [[a, c, e], [b, d, f], [0, 0, 1]])
    # Return the final matrix
    return matrix
def matrix_to_transform(matrix, precision_abcd=3, precision_ef=0):
    # Extract matrix elements
    a, c, e = matrix[0]
    b, d, f = matrix[1]
    
    # Round a, b, c, d elements to specified precision
    # Adding 0 changes -0 to 0
    a = round(a, precision_abcd) + 0
    b = round(b, precision_abcd) + 0
    c = round(c, precision_abcd) + 0
    d = round(d, precision_abcd) + 0
    
    # Round e, f elements to specified precision
    e = round(e, precision_ef) + 0
    f = round(f, precision_ef) + 0
    
    # Construct transform string
    transform = f"matrix({a} {b} {c} {d} {e} {f})"
    return transform.encode('utf-8')

# Replace a list of spans with a list of replacement strings
def Replace_Spans(string,spans,repls):
    # Sort in order
    zipped = zip(spans, repls)
    sorted_zipped = sorted(zipped, key=lambda x: x[0][0])
    spans, repls = zip(*sorted_zipped)
        
    repls = iter(repls)
    result = []
    last_end = 0
    for start, end in spans:
        result.append(string[last_end:start])
        result.append(next(repls))
        last_end = end
    result.append(string[last_end:])
    return rb''.join(result)
    
# Turn numbers into shorter standard formats
class CompareNumericFuzzy2(Compare):
    @staticmethod
    def filter(contents):
        prec_xy   = 0;
        prec_trfm = 3;
        
        # Standardize transforms to matrix()
        spans = []; repls = []
        tfm_pattern = rb'\btransform\s*=\s*(["\'])(.+?)\1';
        tfms = list(re.finditer(tfm_pattern,contents))
        for m in tfms:
            spans.append(m.span())
            tcnts = m.group(1) # contents of transform tag
            newstr= matrix_to_transform(transform_to_matrix(tcnts),
                       precision_abcd=prec_trfm, precision_ef=prec_xy)
            repls.append(b'transform="' + newstr + b'"')
        contents2 = Replace_Spans(contents,spans,repls)
        
        # Round other numbers to 0 digits, ignoring numbers in transforms
        nums = list(re.finditer(rb"-?\d+\.\d+(e[+-]\d+)?", contents2));
        tfms = list(re.finditer(tfm_pattern,               contents2))
        tfms = [mt.span() for mt in tfms]
        spans = []; repls = []
        ti=0;  # current transform we are looking at
        for m in nums:
            s, e = m.span()
            while ti<len(tfms) and tfms[ti][1] <= e:
                ti+=1
            intfm = ti<len(tfms) and s>tfms[ti][0] and e<tfms[ti][1]  # in next tfm
            # print((m.group(0),intfm))
            if not(intfm):
                fmt = b"%." + f"{prec_xy}".encode('utf-8') + b"f";
                repl = fmt % (float(m.group(0))+0) # Adding 0 changes -0 to 0
                spans.append((s,e))
                repls.append(repl)
        contents3 = Replace_Spans(contents2,spans,repls)
        contents = contents3
        
        # func = lambda m: b"%.1f" % (float(m.group(0))) 
        # contents = re.sub(rb"\d+\.\d+(e[+-]\d+)?", func, contents)
        contents = re.sub(rb"(\d\.\d+?)0+\b", rb"\1", contents)
        contents = re.sub(rb"(\d)\.0+(?=\D|\b)", rb"\1", contents)
        
        # Remove empty dx="0" or dy="0" values and similar
        contents = re.sub(rb'\b(dx|dy)\s*=\s*(["\'])(-?0(\.0)?)\2',rb'',contents)
        
        return contents
    
# Remove the content of images for the Autoexporter, along with some header info
class CompareImages(Compare):
    @staticmethod
    def filter(contents):
        contents = re.sub(rb'data:image\/png;base64,(.*?)"',
                          rb'data:image/png;base64,"',contents)
        contents = re.sub(rb'image\/svg\+xml',rb'',contents) # header for different versions
        contents = re.sub(b'sodipodi:docname="[^"]*"', b'sodipodi:docname=""', contents)
        return contents
        
    


if testflattentext:
    class TestFlattenerText(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        comparisons = [flattenerargs]
        compare_file = ['svg/'+flattentext]

if testflattenrest:
    class TestFlattenerRest(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        comparisons = [flattenerargs]
        compare_file = ['svg/'+flattenrest]
    
if testflattenpapers:
    class TestFlattenerPapers(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
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
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=g5224","--tab=correction")
        ]
if testscalecorrection2:
    class TestScaleCorrection2(ComparisonMixin, TestCase):  
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname2]
        comparisons = [
            ("--id=g109153","--id=g109019","--tab=correction")
        ]

if testscalematching:
    class TestScaleMatching(ComparisonMixin, TestCase):
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=rect5248","--id=g4982","--tab=matching")
        ]
if testscalefixed:
    class TestScaleFixed(ComparisonMixin, TestCase):
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=g4982","--tab=scaling",'--hscale=120','--vscale=80')
        ]
    
if testghoster:
    class TestGhoster(ComparisonMixin, TestCase):
        effect_class = TextGhoster
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds(),CompareURLs()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=text28136",)
        ]
  
if testcbc:
    class TestCBC(ComparisonMixin, TestCase):
        effect_class = CombineByColor
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=layer1",)
        ]
    
if testfm:
    class TestFM(ComparisonMixin, TestCase):
        effect_class = FavoriteMarkers
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=path6928","--id=path6952","--smarker=True","--tab=markers")
        ]

if testhomogenizer:
    class TestHomogenizer(ComparisonMixin, TestCase):
        effect_class = Homogenizer
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=layer1","--fontsize=7","--setfontsize=True","--fixtextdistortion=True","--fontmodes=2", \
              "--setfontfamily=True","--fontfamily=Avenir",\
              "--setstroke=True","--setstrokew=0.75","--strokemodes=2","--fusetransforms=True")
        ]

if testhomogenizer2:
    class TestHomogenizer2(ComparisonMixin, TestCase):
        effect_class = Homogenizer
        compare_filters = [CompareNumericFuzzy2(),CompareWithoutIds()]
        compare_file = ['svg/'+fname2]
        comparisons = [
            ("--id=layer1","--fontsize=7","--setfontsize=True","--fixtextdistortion=True","--fontmodes=2", \
              "--setfontfamily=True","--fontfamily=Avenir",\
              "--setstroke=True","--setstrokew=0.75","--strokemodes=2","--fusetransforms=True")
        ] 

if testae:
    class TestAutoExporter(ComparisonMixin, TestCase):
        effect_class = AutoExporter
        compare_filters = [CompareNumericFuzzy2(),
                           CompareWithoutIds(),CompareURLs(),
                           CompareImages()]
        compare_file = ['svg/'+aename]
        comparisons = [aeargs]  
        
        
if testaemp:
    class TestAutoExporterMP1(ComparisonMixin, TestCase):
        effect_class = AutoExporter
        compare_filters = [CompareNumericFuzzy2(),
                           CompareWithoutIds(),CompareURLs(),
                           CompareImages()]
        compare_file = ['svg/'+aepages]
        comparisons = [aeargs+("--testpage=1",)]
    class TestAutoExporterMP2(ComparisonMixin, TestCase):
        effect_class = AutoExporter
        compare_filters = [CompareNumericFuzzy2(),
                           CompareWithoutIds(),CompareURLs(),
                           CompareImages()]
        compare_file = ['svg/'+aepages]
        comparisons = [aeargs+("--testpage=2",)]  




if __name__ == "__main__":
    import sys, inspect
    mywd = os.getcwd();
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
                        os.chdir(mywd)
                        shutil.copyfile(os.path.abspath(pout2),os.path.abspath(pout))
                        print(pout)
    # dh.write_debug()