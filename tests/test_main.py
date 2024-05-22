# coding=utf-8

STORE_REFS = False
fname = 'Other_tests.svg'
fname2 = 'Other_tests_nonuniform.svg'
aename = 'Autoexporter_tests.svg'
aepages = 'Multipage_nonuniform.svg'

MAXPAPERS = 0
flattentext = 'Text_tests.svg'
flattenrest = 'Acid_tests.svg';
flattenflow = 'Flow_tests.svg';
priority_flatten = ['']
exclude_flatten = ['Ohtani_SA_2019_Deep_group.svg',flattentext,flattenrest,fname,aename]

flattenerargs = ("--id=layer1","--testmode=True")
aeargs = ("--testmode=True",)

version = '1.3'
usepango = True
lprofile = False

testflattentext,testflattentextdebug, testflattenrest,testflattenflow,testflattenpapers,testscalecorrection,testscalecorrection2,\
testscalematching,testscalefixed,testghoster,testcbc,testfm,testhomogenizer,testhomogenizer2, testae,testaemp = (False,)*16

testflattentext     = True;
testflattentextdebug = True;
testflattenflow     = True; 
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
testaemp            = True;
testae              = True;

import os, sys, re
vpaths = {'1.0' : 'D:\\Inkscapes\\inkscape-1.0.2-2-x64',
          '1.1' : 'D:\\Inkscapes\\inkscape-1.1.2_2022-02-05_b8e25be833-x64',
          '1.2' : 'D:\\Inkscapes\\inkscape-1.2.2_2022-12-09_732a01da63-x64', 
          '1.3' : 'D:\\Inkscapes\\inkscape-1.3.1_2023-11-16_91b66b0783-x64',
          '1.3e': 'D:\\Inkscapes\\inkscape-1.3_2023-07-21_0e150ed6c4-x64_extensions',
          '1.4' : 'D:\\Inkscapes\\inkscape-1.4-dev_2024-03-31_9b4d34f-x64',
          '1.4e': 'D:\\Inkscapes\\inkscape-1.4-dev_2023-09-22_79074f2-x64_extensions'}

if 'TESTMAINVERSION' in os.environ:
    version = os.environ['TESTMAINVERSION']
if version=='1.0':
    os.environ["SI_FC_DIR"] = os.path.join(vpaths['1.1'],'bin')
    # Font selection changed after 1.0, use 1.1's fc for consistency

sys.path += [os.path.join(vpaths[version],'share\\inkscape\\extensions')]
sys.path += [os.path.join(vpaths[version],'bin')]
sys.path += [os.path.join(os.path.split(os.path.split(__file__)[0])[0],'scientific_inkscape')  ]
sys.path += [os.path.join(vpaths[version],'lib\\python3.10')]
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
# from inkex.tester.filters import CompareWithoutIds
os.environ['SI_TESTING_VERSION'] = version   # needed to avoid circular imports
import tester_mods  # noqa
from tester_mods import CompareNumericFuzzy2, CompareImages

if testflattentext:
    class TestFlattenerText(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),]
        comparisons = [flattenerargs]
        compare_file = ['svg/'+flattentext]
        

if testflattentextdebug:
    class TestFlattenerTextDebug(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),]
        comparisons = [flattenerargs+("--debugparser=True",)]
        compare_file = ['svg/'+flattentext]
        
if testflattenflow:
    class TestFlattenerFlow(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),]
        comparisons = [flattenerargs+("--debugparser=True",)]
        compare_file = ['svg/'+flattenflow]

if testflattenrest:
    class TestFlattenerRest(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),]
        comparisons = [flattenerargs]
        compare_file = ['svg/'+flattenrest]

    
if testflattenpapers:
    def get_files(dirin):
        return [os.path.join(os.path.abspath(dirin), f.name) for f in os.scandir(dirin) if f.name.endswith('.svg')]
    class TestFlattenerPapers(ComparisonMixin, TestCase):
        effect_class = FlattenPlots
        compare_filters = [CompareNumericFuzzy2(),]
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
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=g5224","--tab=correction")
        ]
if testscalecorrection2:
    class TestScaleCorrection2(ComparisonMixin, TestCase):  
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname2]
        comparisons = [
            ("--id=g109153","--id=g109019","--tab=correction")
        ]

if testscalematching:
    class TestScaleMatching(ComparisonMixin, TestCase):
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=rect5248","--id=g4982","--tab=matching")
        ]
if testscalefixed:
    class TestScaleFixed(ComparisonMixin, TestCase):
        effect_class = ScalePlots
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=g4982","--tab=scaling",'--hscale=120','--vscale=80')
        ]
    
if testghoster:
    class TestGhoster(ComparisonMixin, TestCase):
        effect_class = TextGhoster
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=text28136",)
        ]
  
if testcbc:
    class TestCBC(ComparisonMixin, TestCase):
        effect_class = CombineByColor
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=layer1",)
        ]
    
if testfm:
    class TestFM(ComparisonMixin, TestCase):
        effect_class = FavoriteMarkers
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=path6928","--id=path6952","--smarker=True","--tab=markers")
        ]

if testhomogenizer:
    class TestHomogenizer(ComparisonMixin, TestCase):
        effect_class = Homogenizer
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname]
        comparisons = [
            ("--id=layer1","--fontsize=7","--setfontsize=True","--fixtextdistortion=True","--fontmodes=2", \
              "--setfontfamily=True","--fontfamily=Avenir",\
              "--setstroke=True","--setstrokew=0.75","--strokemodes=2","--fusetransforms=True")
        ]

if testhomogenizer2:
    class TestHomogenizer2(ComparisonMixin, TestCase):
        effect_class = Homogenizer
        compare_filters = [CompareNumericFuzzy2(),]
        compare_file = ['svg/'+fname2]
        comparisons = [
            ("--id=layer1","--fontsize=7","--setfontsize=True","--fixtextdistortion=True","--fontmodes=2", \
              "--setfontfamily=True","--fontfamily=Avenir",\
              "--setstroke=True","--setstrokew=0.75","--strokemodes=2","--fusetransforms=True")
        ] 
        
if testaemp:
    class TestAutoExporterMP1(ComparisonMixin, TestCase):
        effect_class = AutoExporter
        compare_filters = [CompareNumericFuzzy2(),
                           CompareImages()]
        compare_file = ['svg/'+aepages]
        comparisons = [aeargs+("--testpage=1",)]
    class TestAutoExporterMP2(ComparisonMixin, TestCase):
        effect_class = AutoExporter
        compare_filters = [CompareNumericFuzzy2(),
                           CompareImages()]
        compare_file = ['svg/'+aepages]
        comparisons = [aeargs+("--testpage=2",)]  
 
       
if testae:
    class TestAutoExporter(ComparisonMixin, TestCase):
        effect_class = AutoExporter
        compare_filters = [CompareNumericFuzzy2(),
                           CompareImages()]
        compare_file = ['svg/'+aename]
        comparisons = [aeargs]  
        


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