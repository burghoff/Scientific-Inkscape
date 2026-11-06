import os
version = os.environ['SI_TESTING_VERSION'] 
import inkex.tester
import re

from inkex.tester.xmldiff import xmldiff,xml,text_compare
hasxpath_ids = hasattr(inkex.tester.xmldiff,'xpath_ids')
    
def mod_xmldiff(data_a,data_b):
    if data_a == data_b:  # identical bytes: nothing to parse or walk
        return "", DeltaLogger()
    if not hasxpath_ids:
        diff_xml, delta = xmldiff_xpath(data_a, data_b)
    else:
        diff_xml, delta = xmldiff(data_a, data_b)
        
    toremove = []
    
    for x, (value_a, value_b) in enumerate(delta):
        # print( (value_a, value_b))
        
        # For x values, due to kerning measurement differences we allow for up to 1 pixel
        if value_a is not None and value_b is not None and len(value_a)>0 and len(value_b)>0 and \
           ((value_a[1]=='x' and value_b[1]=='x') or (value_a[1]=='y' and value_b[1]=='y')):
            try:
                if abs(float(value_a[2])-float(value_b[2]))<=1:
                    toremove.append((value_a, value_b))
            except:
                pass
        elif value_a is not None and value_b is not None and len(value_a)>2 and len(value_b)>2 and \
           value_a[1]=='transform' and value_b[1]=='transform' and \
           value_a[2].startswith('matrix(') and value_b[2].startswith('matrix('):
            # Like x and y, the translation may differ by up to 1 pixel
            try:
                ma = [float(v) for v in value_a[2][7:-1].split()]
                mb = [float(v) for v in value_b[2][7:-1].split()]
                if len(ma)==len(mb)==6 and ma[:4]==mb[:4] and \
                   all(abs(va-vb)<=1 for va, vb in zip(ma[4:], mb[4:])):
                    toremove.append((value_a, value_b))
            except ValueError:
                pass
        elif value_a is not None and value_b is not None and len(value_a)>2 and len(value_b)>2 and \
            'Cambria' in value_a[2]:
            if value_a[2].replace('Cambria Math','Cambria')==value_b[2].replace('Cambria Math','Cambria'):
                toremove.append((value_a, value_b))
        elif (os.environ.get("HASPANGO")=='False') and \
            value_a is not None and value_b is not None and len(value_a)>0 and len(value_b)>0 and \
           ((value_a[1]=='height' and value_b[1]=='height')):
            # Cap height slightly different
            try:
                if abs(float(value_a[2])-float(value_b[2]))<=1:
                    toremove.append((value_a, value_b))
            except:
                pass
    for r in toremove:
        delta.remove(r)
    return diff_xml, delta
inkex.tester.xmldiff = mod_xmldiff


# Reference files pass through the compare filters on every run, which costs
# about as much as filtering the output. The filtered reference is kept in the
# temp directory, keyed by its contents, the filters and this file, so it is
# only filtered again when one of those changes. assertCompare passes
# is_saving=False for the reference file only.
_apply_compare_filters = inkex.tester.ComparisonMixin._apply_compare_filters
def cached_compare_filters(self, data, is_saving=None):
    if is_saving is not False or not isinstance(data, bytes):
        return _apply_compare_filters(self, data, is_saving)
    import hashlib, tempfile
    key = hashlib.sha1(data)
    key.update(repr([(type(f).__name__, f.options) for f in self.compare_filters]).encode("utf-8"))
    with open(__file__, "rb") as f:
        key.update(f.read())
    cdir = os.path.join(tempfile.gettempdir(), "si_tests_filtered_refs")
    cfile = os.path.join(cdir, key.hexdigest())
    try:
        with open(cfile, "rb") as f:
            return f.read()
    except FileNotFoundError:
        pass
    data = _apply_compare_filters(self, data, is_saving)
    os.makedirs(cdir, exist_ok=True)
    tmp = cfile + "." + str(os.getpid())  # written whole, then renamed, so that concurrent runs never read a partial file
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, cfile)
    return data
inkex.tester.ComparisonMixin._apply_compare_filters = cached_compare_filters
        


class DeltaLogger(list):
    """A record keeper of the delta between two svg files"""

    def append_tag(self, tag_a, tag_b, ida, idb):
        """Record a tag difference"""
        if tag_a:
            tag_a = f"<{tag_a}.../>"
        if tag_b:
            tag_b = f"<{tag_b}.../>"
        self.append(((ida, tag_a), (idb, tag_b)))

    def append_attr(self, attr, value_a, value_b, a_id, b_id):
        """Record an attribute difference"""

        def _prep(val, idv):
            if val:
                if attr == "d":
                    return [attr] + inkex.Path(val).to_arrays()
                return (idv, attr, val)
            return val

        # Only append a difference if the preprocessed values are different.
        # This solves the issue that -0 != 0 in path data.
        prep_a = _prep(value_a, a_id)
        prep_b = _prep(value_b, b_id)
        if prep_a != prep_b:
            self.append((prep_a, prep_b))

    def append_text(self, text_a, text_b, ida, idb):
        """Record a text difference"""
        self.append(((ida, text_a), (idb, text_b)))

    def __bool__(self):
        """Returns True if there's no log, i.e. the delta is clean"""
        return not self.__len__()

    __nonzero__ = __bool__

    def __repr__(self):
        if self:
            return "No differences detected"
        return f"{len(self)} xml differences"

from lxml import etree
from io import BytesIO
ctag = etree.Comment

def to_lxml(data):
    """Convert string or bytes to lxml parsed root node"""
    if isinstance(data, str):
        data = data.encode("utf8")
    if isinstance(data, bytes):
        return etree.parse(BytesIO(data)).getroot()
    return data


def xmldiff_xpath(data1, data2):
    """Create an xml difference, will modify the first xml structure with a diff"""
    
    # from dhelpers import ctic, ctoc
    # ctic()
    
    xml1, xml2 = to_lxml(data1), to_lxml(data2)

    memo1 = xpath_ids(xml1)
    memo2 = xpath_ids(xml2)

    delta = DeltaLogger()
    _xmldiff(xml1, xml2, delta, memo1, memo2)
    
    # ctoc()
    
    return xml.tostring(xml1).decode("utf-8"), delta

def xpath_ids(svg):
    """When comparing two documents, replace all IDs with a test ID related to the xpath location"""

    # Prune comments
    for el in svg.iter():
        if el.tag == ctag:
            el.getparent().remove(el)

    # Identify all the xpaths
    siter = svg.iter()
    next(siter, None)
    # xps = {svg:'/*'}
    xps = {svg: ""}
    for el in siter:
        myp = el.getparent()
        # xps[el] = xps[myp]+'/*[{0}]'.format(myp.index(el)+1)
        xps[el] = xps[myp] + "/{0}".format(myp.index(el) + 1)
        # Simplified version of true xpath for clarity

    import re

    urlpat = r"url\(#[^\)]*\)"
    classpat = r"\.(.*?)\{"
    xlinkatts = ["{http://www.w3.org/1999/xlink}href", "href"]
    bareids = {"{http://www.inkscape.org/namespaces/inkscape}stockid", "class"}
    styletag = "{http://www.w3.org/2000/svg}style"
    repl_ids = dict()

    fid = lambda id1, id2: f"xpId{id1}{'_' if id2 else ''}{id2}"
    # Collect all ids present in document in order and decide replacement avlues
    for el in svg.iter():
        oldid = el.get("id")
        xp = xps[el]
        if oldid is None:
            # No ids: assign one
            newid = fid(xp, "")
            el.set("id", newid)
        elif not (oldid.startswith("xpId")) and oldid not in repl_ids:
            # Id not already replaced: decide replacement
            repl_ids[oldid] = fid(xp, "")

    # Now, find any references in attributes/text that were not already assigned new IDs
    for el in svg.iter():
        count = 0
        for n, v in el.attrib.items():
            # ids in xlink:href values
            if v.startswith("#") and n in xlinkatts:
                oldid = v[1:]
                if oldid not in repl_ids:
                    repl_ids[oldid] = fid(xp, count)
                    count += 1
            elif n in bareids:
                oldid = v
                if oldid not in repl_ids:
                    repl_ids[oldid] = fid(xp, count)
                    count += 1
            # ids in url(#)'s
            elif v is not None and len(re.findall(urlpat, v)) > 0:
                ms = re.findall(urlpat, v)
                for m in ms:
                    oldid = m[5:-1]
                    if oldid not in repl_ids:
                        repl_ids[oldid] = fid(xp, count)
                        count += 1
        if el.tag == styletag:
            # ids in css style text url(#)'s
            if el.text is not None and len(re.findall(urlpat, el.text)) > 0:
                ms = re.findall(urlpat, el.text)
                for m in ms:
                    oldid = m[5:-1]
                    if oldid not in repl_ids:
                        repl_ids[oldid] = fid(xp, count)
                        count += 1

            # class ids in css style text .id{
            if el.text is not None and len(re.findall(classpat, el.text)) > 0:
                ms = re.findall(classpat, el.text)
                for m in ms:
                    oldid = m.strip()
                    if oldid not in repl_ids:
                        repl_ids[oldid] = fid(xp, count)
                        count += 1

    # Make all replacements
    oldids2 = {"#" + v for v in repl_ids.keys()}  # oldids with #
    oldids3 = {"url(#" + v + ")" for v in repl_ids.keys()}  # oldids with url(#...)
    for el in svg.iter():
        for n, v in el.attrib.items():
            if n == "id" and v in repl_ids:
                # print(v,repl_ids[v])
                el.attrib[n] = repl_ids[v]
                # print(el.get('id'))
            elif v in oldids2 and n in xlinkatts:
                el.attrib[n] = "#" + repl_ids[v[1:]]
            elif n in bareids:
                el.attrib[n] = repl_ids[v]
            elif "url(#" in v:  # precheck for speed
                ms = re.findall(urlpat,v)
                for m in ms:
                    if m in oldids3:
                        el.attrib[n] = el.attrib[n].replace(
                            m, "url(#" + repl_ids[m[5:-1]] + ")"
                        )
        if el.tag == styletag:
            if el.text is not None and "url(#" in el.text:
                ms = re.findall(urlpat,el.text)
                for m in ms:
                    if m in oldids3:
                        el.text = el.text.replace(
                            m, "url(#" + repl_ids[m[5:-1]] + ")"
                        )
                ms = re.findall(classpat, el.text)
                for m in ms:
                    if m.strip() in repl_ids:
                        el.text = el.text.replace(m, repl_ids[m.strip()]) + " "
    memo = {v: k for k, v in repl_ids.items()}
    return memo


def _xmldiff(xml1, xml2, delta, memo1, memo2):
    id1 = memo1.get(xml1.get("id"), xml1.get("id"))
    id2 = memo2.get(xml2.get("id"), xml2.get("id"))
    if xml1.tag != xml2.tag:
        # xml1.tag = f"{xml1.tag}XXX{xml2.tag}"
        delta.append_tag(xml1.tag, xml2.tag, id1, id2)
    for name, value in xml1.attrib.items():
        if name not in xml2.attrib:
            delta.append_attr(name, xml1.attrib[name], None, id1, id2)
            xml1.attrib[name] += "XXX"
        elif xml2.attrib.get(name) != value:
            delta.append_attr(
                name, xml1.attrib.get(name), xml2.attrib.get(name), id1, id2
            )
            xml1.attrib[name] = f"{xml1.attrib.get(name)}XXX{xml2.attrib.get(name)}"
    for name, value in xml2.attrib.items():
        if name not in xml1.attrib:
            delta.append_attr(name, None, value, id1, id2)
            xml1.attrib[name] = "XXX" + value
    if not text_compare(xml1.text, xml2.text):
        delta.append_text(xml1.text, xml2.text, id1, id2)
        xml1.text = f"{xml1.text}XXX{xml2.text}"
    if not text_compare(xml1.tail, xml2.tail):
        delta.append_text(xml1.tail, xml2.tail, id1, id2)
        xml1.tail = f"{xml1.tail}XXX{xml2.tail}"

    # Get children and pad with nulls
    children_a = list(xml1)
    children_b = list(xml2)
    children_a += [None] * (len(children_b) - len(children_a))
    children_b += [None] * (len(children_a) - len(children_b))

    for child_a, child_b in zip(children_a, children_b):
        if child_a is None:  # child_b exists
            delta.append_tag(
                None, child_b.tag, None, memo2.get(child_b.get("id"), child_b.get("id"))
            )
        elif child_b is None:  # child_a exists
            delta.append_tag(
                child_a.tag, None, memo1.get(child_a.get("id"), child_a.get("id")), None
            )
        else:
            _xmldiff(child_a, child_b, delta, memo1, memo2)
            

from inkex.tester.filters import Compare
class CompareAEMarker(Compare):
    """Blank the path in the Autoexporter's original-file marker: it is the
    absolute input path, so it depends on the machine, the checkout and even
    the launching shell's separators. The hash after it is still compared."""
    @staticmethod
    def filter(contents):
        return re.sub(rb"si_ae_original_filename: .*?, hash:", rb"si_ae_original_filename: PATH, hash:", contents)

# Replace all ids contained in urls in the order they appear in the document
# class CompareURLs(Compare):
#     @staticmethod
#     def filter(contents):
#         # print(contents)
#         myid = b'SItestURL'
#         def findurl(x):
#             # Gets the first url#( ... ) content
#             m = re.findall(rb"url\(\#(.*?)\)",x)
#             g = [mv for mv in m if myid not in mv]  # exclude already substituted
#             if len(g)==0:
#                 return None
#             else:
#                 return g[0]
#         f = findurl(contents)
#         n = 0;
#         while f is not None:
#             newid = myid+(b"%.0f" % n);
#             contents = re.sub(rb'"'      +f+rb'"',  rb'"'     +newid+rb'"',contents)
#             contents = re.sub(rb'url\(\#'+f+rb'\)',rb'url\(\#'+newid+rb'\)',contents)
#             n += 1
#             f = findurl(contents)
#         return contents
    
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
# Turn numbers into shorter standard formats
class CompareNumericFuzzy2(Compare):
    tfm_pattern = rb'\btransform\s*=\s*(["\'])(.+?)\1'
    # a transform, or a decimal number outside one
    tfm_or_num = re.compile(tfm_pattern + rb"|(-?\d+\.\d+(?:e[+-]\d+)?)")

    @staticmethod
    def filter(contents):
        prec_else   = 0;
        prec_trfm = 3;
        
        # Standardize transforms to matrix()
        def tfm(m):
            tcnts = m.group(2) # contents of transform tag
            newstr= matrix_to_transform(transform_to_matrix(tcnts),
                       precision_abcd=prec_trfm, precision_ef=prec_else)
            return b'transform="' + newstr + b'"'
        contents = re.sub(CompareNumericFuzzy2.tfm_pattern, tfm, contents)
        
        # Round other numbers to 0 digits, ignoring numbers in transforms
        fmt = b"%." + f"{prec_else}".encode('utf-8') + b"f";
        def num(m):
            if m.group(3) is None:
                return m.group(0)  # a transform
            return fmt % (float(m.group(3))+0) # Adding 0 changes -0 to 0
        contents = CompareNumericFuzzy2.tfm_or_num.sub(num, contents)
        
        contents = re.sub(rb"(\d\.\d+?)0+\b", rb"\1", contents)
        contents = re.sub(rb"(\d)\.0+(?=\D|\b)", rb"\1", contents)
        
        # Remove empty dx="0" or dy="0" values and similar
        contents = re.sub(rb'\b(dx|dy)\s*=\s*(["\'])(-?0(\.0)?)\2',rb'',contents)
        
        # Delete identity transforms
        contents = re.sub(rb'transform\s*=\s*"matrix\(1 0 0 1 0 0\)"', rb'', contents)

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