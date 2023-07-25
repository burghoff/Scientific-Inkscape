# Inkscape Auto-Exporter, by David Burghoff
# Service that checks a folder for changes in svg files, and then exports them
# automatically to another folder in multiple formats.

DEBUG = False
WHILESLEEP = 0.25;


IMAGE_WIDTH = 175;
IMAGE_HEIGHT = IMAGE_WIDTH*0.7;


try:
    import sys, subprocess, os, threading, time, copy, pickle, chardet
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        guitype = 'gtk'
    except:
        try:
            import tkinter as tk
            from tkinter import filedialog
            guitype = 'tkinter'
        except:
            guitype = 'terminal'
    
    from dhelpers import si_tmp
    aes = si_tmp(filename='si_gv_settings.p')
    with open(aes, "rb") as f:
        input_options = pickle.load(f)
    os.remove(aes)
    from autoexporter import orig_key
    from autoexporter import dup_key
                
    bfn       = input_options.inkscape_bfn
    sys.path += input_options.syspath
    PORTNUMBER = input_options.portnum
    
    import dhelpers as dh
    import sys, webbrowser, urllib, pathlib
    import inkex

    current_script_directory = os.path.dirname(os.path.abspath(__file__))
    sys.path += [os.path.join(current_script_directory,'packages')]
    
    def file_uri_to_path(file_uri, path_class=pathlib.PurePath):
        # https://stackoverflow.com/questions/5977576/is-there-a-convenient-way-to-map-a-file-uri-to-os-path
        """
        This function returns a pathlib.PurePath object for the supplied file URI.
    
        :param str file_uri: The file URI ...
        :param class path_class: The type of path in the file_uri. By default it uses
            the system specific path pathlib.PurePath, to force a specific type of path
            pass pathlib.PureWindowsPath or pathlib.PurePosixPath
        :returns: the pathlib.PurePath object
        :rtype: pathlib.PurePath
        """
        windows_path = isinstance(path_class(),pathlib.PureWindowsPath)
        file_uri_parsed = urllib.parse.urlparse(file_uri)
        file_uri_path_unquoted = urllib.parse.unquote(file_uri_parsed.path)
        if windows_path and file_uri_path_unquoted.startswith("/"):
            result = path_class(file_uri_path_unquoted[1:])
        else:
            result = path_class(file_uri_path_unquoted)
        if result.is_absolute() == False:
            raise ValueError("Invalid file uri {} : resulting path {} not absolute".format(
                file_uri, result))
        return result
    
    global refreshapp
    refreshapp = False
    def trigger_refresh():
        global refreshapp
        refreshapp = True
    
    def Make_Flask_App():
        import warnings
        warnings.simplefilter("ignore", DeprecationWarning); # prevent warning that process is open
        from flask import Flask, request, url_for, jsonify, send_from_directory
        app = Flask(__name__)
        
        global folder_dict
        folder_dict = dict();
        
        @app.route('/images/<folder>/<path:path>')
        def send_image(folder,path):
            global folder_dict
            return send_from_directory(os.path.abspath(folder_dict[folder]), path)

        @app.route("/")
        def index():
            global temp_dir
            gloc = os.path.join(temp_dir,"Gallery.html");
            with open(gloc, "rb") as f:
                gallery = f.read();
                global fileuris
                nnames = [];
                for v in fileuris:
                    svg_file = file_uri_to_path(v)
                    folder, file = os.path.split(svg_file)
                    
                    global folder_dict
                    if folder not in folder_dict.values():
                        k = os.path.split(temp_dir)[-1]+'-dir'+str(len(folder_dict));
                        folder_dict[k] = folder
                    else:
                        k = next(key for key, value in folder_dict.items() if value == folder)
                    nnames.append(url_for('send_image', path=file, folder=k))
                
                new_string = gallery
                for ii, fu in enumerate(fileuris):
                    new_string = new_string.replace(bytes('data-src="{0}"'.format(str(fu)),        'utf-8'),
                                                    bytes('data-src="{0}"'.format(str(nnames[ii])),'utf-8'))
                return new_string
        @app.route("/stop")
        def stop():
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()
            return "Server shutting down..."
        
        @app.route("/process", methods=["GET"])
        def process():
            param = request.args.get("param")
            svg_file = file_uri_to_path(param)
            if svg_file is not None:
                print('Opening'+str(svg_file))
                
                if str(svg_file).endswith('.emf'):
                    subprocess.run([bfn, svg_file]);
                    return f"The parameter received is: {param}"
                
                with OpenWithEncoding(svg_file) as f:
                    file_content = f.read()
                    if dup_key in file_content:
                        global temp_dir
                        deembedsmade = False
                        while not(deembedsmade):
                            deembeds = os.path.join(temp_dir, 'deembeds')
                            deembedsmade = os.path.exists(deembeds)
                            if not(deembedsmade):
                                os.mkdir(deembeds)
                                
                        tsvg = os.path.join(deembeds,'tmp_'+str(len(os.listdir(deembeds)))+'.svg')
                        svg = dh.svg_from_file(svg_file);
                        
                        for d in svg.descendants2():
                            if isinstance(d,inkex.TextElement) and d.text is not None and dup_key in d.text:
                                dupid = d.text[len(dup_key+': '):]
                                dup = svg.getElementById(dupid)
                                if dup is not None:
                                    dup.delete();
                                g = d.getparent();
                                d.delete();
                                g.set('display',None) # office converts to att
                                g.cstyle['display'] = None
                                list(g)[0].set_id(dupid)
                                dh.ungroup(g);
                                
                        
                        
                        dh.overwrite_svg(svg,tsvg)
                        subprocess.run([bfn, tsvg]);
                    else:
                        subprocess.run([bfn, svg_file]);
                
            return f"The parameter received is: {param}"
        
        @app.route('/check_for_refresh')
        def check_for_refresh():
            global refreshapp, lastupdate, openedgallery
            openedgallery = True
            if refreshapp:
                refreshapp = False
                make_svg_display()
                lastupdate = time.time();
            return jsonify(lastupdate=lastupdate)
            
        def run_flask():
            app.run(port = PORTNUMBER)
        from threading import Thread
        thread = Thread(target=run_flask)
        thread.start()
        return app
    
    
    global temp_dir
    temp_dir = si_tmp(dirbase='gv');
    
    import os
    import zipfile
    import shutil
    
    def make_svg_display():
        import os
    
        # Create the HTML file
        global temp_dir
        gloc = os.path.join(temp_dir,"Gallery.html");
        with open(gloc, "w") as file:
        # Write the HTML header
            file.write('<html translate="no">\n')
            
            # Define the CSS styles
            css_styles = """
            <style>
            div.gallery {
              margin: 5px;
              border: 1px solid #ccc;
              float: none;
              width: IMAGE_WIDTHpx;
              display: inline-block;
              vertical-align: top; /* Add this line to align the tops */
            }
            
            div.gallery:hover {
              border: 1px solid #777;
            }
            
            div.gallery img {
              object-fit: contain;
              width: IMAGE_WIDTHpx;
              height: IMAGE_HEIGHTpx;
            }
            
            div.desc {
              padding: 15px;
              text-align: center;
              word-wrap: break-word;
            }
            body {
                font-family: Roboto, Arial, sans-serif;
                font-size: 14;
              }
            @supports not (-ms-ime-align: auto) {
              details summary { 
                cursor: pointer;
              }
            
              details summary > * { 
                display: inline;
              }
            
              /* Plus any other <details>/<summary> styles you want IE to ignore.
            }
            </style>
            """
            css_styles = css_styles.replace('IMAGE_WIDTH', str(IMAGE_WIDTH))
            css_styles = css_styles.replace('IMAGE_HEIGHT',str(IMAGE_HEIGHT))
            # Create the string with the <head>, <style>, and </style> tags
            meta = "<meta name='google' content='notranslate'>\n";
            title = "<title>SVG Gallery</title>\n"
            string = "<head>{0}{1}{2}</head>".format(css_styles,meta,title)
            file.write(string)
            file.write("<body>\n")
        
            
                    
            global fileuris
            fileuris = [];# tii=0;
            global watcher_threads
            # wt2 = [wt for wt in watcher_threads if wt.run_on_fof_done]
            for wt in watcher_threads:
                svg_filenames,thumbnails,header,slidenums,islinked = wt.files[:],wt.thumbnails,wt.header,wt.slidenums,wt.islinked
                
                det = '<details open>' if wt.open_at_load else '<details closed>'
                file.write('<br>'+det+'<summary><h2>'+header+'</h2></summary>\n<div class="serverdown" style="color: #e41a1cff;"></div>')
                # Loop through the SVG filenames and write an img tag for each one
                if wt.run_on_fof_done:
                    for ii, svg in enumerate(svg_filenames):
                        gallery = """
                        <div class="gallery">
                          <a target="_blank" href="#">
                            <img data-src="#" alt="" id='img{2}'>
                          </a>
                          <div class="desc">{4}<a href="http://localhost:{3}/process?param={0}" class="open">{6}</a>{5}</div>
                        </div>
                        """
                        # if any([isinstance(fn,list) for fn in wt.files]):
                        #     return
                        myloc = "file://" + svg;
                        myloc = pathlib.Path(svg).as_uri()
                        tnloc = pathlib.Path(thumbnails[ii]).as_uri()
                        gallery = gallery.replace('data-src="#"','data-src="{0}" class="lazyload"'.format(tnloc))
                        if slidenums is not None:
                            label = 'Slide {0}'.format(slidenums[ii])+'<br>'
                        else:
                            pn = ' ({0})'.format(wt.pagenums[ii]) if wt.pagenums[ii] is not None else ''
                            label = os.path.split(svg)[-1]+pn+'<br>';
                        embed = ''
                        if wt.embeds is not None:
                            if wt.embeds[ii]:
                                embed = pathlib.Path(wt.embeds[ii]).as_uri()
                                embed = '<br><a href="http://localhost:{0}/process?param={1}" class="open">Original</a><br>'.format(str(PORTNUMBER),embed)
                        
                        linked = islinked is not None and islinked[ii]
                        currenttype = 'Current' if os.path.isdir(wt.fof) else 'Linked' if linked else 'Embedded'
                        file.write(gallery.format(myloc,os.path.split(svg)[-1],len(fileuris),str(PORTNUMBER),label,embed,currenttype))
                        fileuris.append(tnloc);
                else:
                    file.write('<br>Processing')
                file.write('</details>')
                
            #<br><a href="http://localhost:5000/stop" id="stop_link">Stop Server</a>
            file.write("""
               <script>
                document.querySelectorAll("a.open").forEach(function(link) {
                    link.addEventListener("click", function(event){
                        event.preventDefault();
                        var xhr = new XMLHttpRequest();
                        xhr.open("GET", this.href, true);
                        xhr.send();
                    });
                });
            
                </script>
                """)
            
            script = """
            <script>
            
            var mylastupdate = Date.now() / 1000;
            setInterval(function(){
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/check_for_refresh');
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        var response = JSON.parse(xhr.responseText);
                        if (response.lastupdate > mylastupdate) {
                            location.reload();
                        }
                    }
                };
                xhr.onerror = function() {
                document.querySelector('.serverdown').innerHTML = "Server is not running, files cannot be opened.";
                };
                xhr.send();
            }, 1000);
            
            document.addEventListener("DOMContentLoaded", function() {
              var lazyImages = [].slice.call(document.querySelectorAll("img.lazyload"));
              var outsideViewImagesQueue = [];
            
              function handleIntersection(entries, observer) {
                  let insideViewImages = entries.filter(entry => entry.isIntersecting).map(entry => entry.target);
                  let outsideViewImages = entries.filter(entry => !entry.isIntersecting).map(entry => entry.target);
                
                  insideViewImages.forEach(function(lazyImage) {
                    lazyImage.src = lazyImage.dataset.src;
                    lazyImage.classList.remove("lazyload");
                    observer.unobserve(lazyImage);
                  });
                
                  // Wait until all inside view images have finished loading
                  Promise.all(insideViewImages.map(img => new Promise((resolve, reject) => {
                    img.onload = resolve;
                    img.onerror = reject;
                  }))).then(() => {
                    // Then load the images outside the view
                    outsideViewImages.forEach(function(lazyImage) {
                      lazyImage.src = lazyImage.dataset.src;
                      lazyImage.classList.remove("lazyload");
                      observer.unobserve(lazyImage);
                    });
                  }).catch(error => {
                    console.error('Some images did not load successfully', error);
                  });
                }
            
              if ("IntersectionObserver" in window) {
                let lazyImageObserver = new IntersectionObserver(handleIntersection);
                lazyImages.forEach(function(lazyImage) {
                  lazyImageObserver.observe(lazyImage);
                });
              } else {
                lazyImages.forEach(function(lazyImage) {
                  lazyImage.src = lazyImage.dataset.src;
                  lazyImage.classList.remove("lazyload");
                });
              }
            });

            </script>
            """
            file.write(script)
            
            # Write the HTML footer
            file.write("</body>\n")
            file.write("</html>\n")
        # return 
        
        print('Gallery: '+pathlib.Path(gloc).as_uri())
        
    # Opens a file with unknown encoding, trying utf-8 first
    # chardet can be slow
    class OpenWithEncoding:
        def __init__(self, filename, mode='r'):
            self.filename = filename
            self.mode = mode
            self.file = None
    
        def __enter__(self):
            try:
                self.file = open(self.filename, self.mode, encoding='utf-8')
            except UnicodeDecodeError:
                with open(self.filename, 'rb') as f:
                    raw_data = f.read()
                    result = chardet.detect(raw_data)  
                    encoding = result['encoding']
    
                self.file = open(self.filename, self.mode, encoding=encoding)
    
            return self.file
    
        def __exit__(self, exc_type, exc_value, traceback):
            if self.file is not None:
                self.file.close()
            return False  # Don't suppress exceptions

    class WatcherThread(threading.Thread):
        # A thread that generates an SVG gallery of files, then watches
        # it for changes
        def __init__(self, file_or_folder,opened=True):
            threading.Thread.__init__(self)
            # self.threadID = threadID
            self.fof = file_or_folder
            self.stopped = False
            self.open_at_load = opened
            self.run_on_fof_done = False

        def get_image_slidenums(self,dirin):
            import os
            import xml.etree.ElementTree as ET
            relsdir = os.path.join(dirin,'ppt','slides','_rels')
            numslides = len(os.listdir(relsdir))
            slide_filenames = [];
            for slide_num in range(1,numslides+1):
                tree = ET.parse(os.path.join(dirin, "ppt", "slides", "_rels", f"slide{slide_num}.xml.rels"))
                root = tree.getroot()
                image_filenames = []
                for elem in root.iter("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                    if elem.attrib["Type"] == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image":
                        image_filenames.append(elem.attrib["Target"])
                slide_filenames.append(image_filenames)
            slide_lookup = {}
            for index, filenames in enumerate(slide_filenames):
                for filename in filenames:
                    slide_lookup[filename] = slide_lookup.get(filename, []) + [index + 1]
            return slide_lookup


        def run_on_fof(self):
            print("Running on file:", self.fof,flush=True)
            global temp_dir
            
            import random
            contentsmade = False
            while not(contentsmade):
                contents = os.path.join(temp_dir, 'contents'+str(random.randint(1, 100000)))
                if not(os.path.exists(contents)):
                    os.mkdir(contents)
                    contentsmade = True
            
            def get_svgs(dirin):
                svg_filenames = []
                for file in os.listdir(dirin):
                  if file.endswith(".svg") or file.endswith(".emf"):
                    svg_filenames.append(os.path.join(dirin,file))
                svg_filenames.sort()
                return svg_filenames

            tndir = os.path.join(contents,'thumbnails')
            if not os.path.exists(tndir):
                os.makedirs(tndir)
            numtns = len(os.listdir(tndir))
            
            if os.path.isfile(self.fof):
                # Unzip the ppt file to the temp directory
                ftype = 'ppt' if self.fof.endswith('.pptx') else 'word'
                with zipfile.ZipFile(self.fof, 'r') as zip_ref:
                    zip_ref.extractall(contents)
                ppt_media_dir = os.path.join(contents, ftype, 'media')
                self.files = get_svgs(ppt_media_dir);
                if ftype=='ppt':
                    self.slidenums = self.get_image_slidenums(contents)
                
                    # Add linked images to self.files
                    linked = [str(file_uri_to_path(k)) for k in self.slidenums.keys() if 'file:' in k];
                    self.files += linked;
                    self.slidenums = {os.path.join(contents,ftype,'media',os.path.basename(k)) \
                                      if 'file:' not in k else str(file_uri_to_path(k)) : v \
                                          for k,v in self.slidenums.items()}
                    
                    # Sort the files by slide number and make slidenums a corresponding list
                    # Duplicates filenames if on multiple slides
                    new_files = []
                    new_slidenums = []
                    for file in self.files:
                        slides = self.slidenums.get(file, [float('inf')])
                        for slide in slides:
                            new_files.append(file)
                            new_slidenums.append(slide)
                    new_files_and_slidenums = sorted(zip(new_files, new_slidenums), key=lambda x: (x[1], x[0]))
                    self.files, self.slidenums = zip(*new_files_and_slidenums)
                    self.files = list(self.files)
                    self.slidenums = list(self.slidenums)
                    self.slidenums = [v if v!=float('inf') else '?' for v in self.slidenums]
                    self.islinked = [f in linked for f in self.files]
                else:
                    self.slidenums = None
                    self.islinked = None
                    self.embeds = None

                self.thumbnails = copy.copy(self.files)
                self.header = self.fof
                print("Temp dir: "+temp_dir,flush=True)
                print(self.files,flush=True)
                
                self.embeds = []
                subfiles = None
                for fn in self.files:
                    ev = False
                    if fn.endswith('.svg'):
                        with OpenWithEncoding(fn) as f:
                            file_content = f.read()
                            if orig_key in file_content:
                                import re
                                key = orig_key + r":\s*(.+?)<"
                                match = re.search(key, file_content);
                                if match:
                                    orig_file = match.group(1)
                                    orig_hash = None
                                    if ', hash: ' in orig_file: # introduced hashing later than orig_key
                                        orig_file, orig_hash = orig_file.split(', hash: ')
                                    if os.path.exists(orig_file):
                                        ev = os.path.abspath(orig_file)
                                    else:
                                        # Check subdirectories of the file's location in case it was moved
                                        
                                        def list_all_files(directory):
                                            for dirpath, dirs, files in os.walk(directory):
                                                for filename in files:
                                                    yield os.path.join(dirpath, filename)
                                        fndir = os.path.split(self.fof)[0]
                                        subfiles = list(list_all_files(fndir)) if subfiles is None else subfiles
                                        from autoexporter import hash_file
                                        for tryfile in subfiles:
                                            if os.path.split(orig_file)[-1]==os.path.split(tryfile)[-1] \
                                               and (orig_hash is None or hash_file(tryfile)==orig_hash):
                                                   ev = os.path.abspath(tryfile)
                                                   break
                                        
                    self.embeds.append(ev)
                self.pagenums = [None]*len(self.files)

            elif os.path.isdir(self.fof):
                self.files = get_svgs(self.fof);
                self.thumbnails = copy.copy(self.files)
                self.header = self.fof
                self.slidenums = None
                self.islinked = None
                self.embeds = None
                
                for ii,fn in enumerate(self.files):
                    tns = []
                    if fn.endswith('.svg'):
                        with OpenWithEncoding(fn) as f:
                            contents = f.read()
                            import re
                            match = re.search(r'<\s*inkscape:page[\s\S]*?>', contents)
                            if match:
                                svg = dh.svg_from_file(fn);
                                pgs = svg.cdocsize.pgs
                                haspgs = svg.cdocsize.inkscapehaspgs 
                                
                                if haspgs and len(pgs)>1:
                                    vbs = [svg.cdocsize.pxtouu(pg.bbpx) for pg in pgs]
                                    for vb in vbs:
                                        svg.set_viewbox(vb)
                                        tnsvg = os.path.join(tndir,str(numtns)+'.svg')
                                        numtns+=1
                                        dh.overwrite_svg(svg,tnsvg)
                                        tns.append(tnsvg)
                    if len(tns)>0:
                        self.files[ii] = [fn]*len(tns)
                        self.thumbnails[ii] = tns
                    else:
                        self.files[ii] = [self.files[ii]]
                        self.thumbnails[ii] = [self.thumbnails[ii]]
                self.files = [fn for fnl in self.files for fn in fnl]
                self.pagenums = [pn if len(tnl)>1 else None for tnl in self.thumbnails for pn in range(1,1+len(tnl))]
                self.thumbnails = [tn for tnl in self.thumbnails for tn in tnl]
                        
            for ii,tn in enumerate(self.thumbnails):
                if tn.endswith('.emf'):
                    tnpng = os.path.join(tndir,str(numtns)+'.png')
                    numtns+=1
                    self.thumbnails[ii] = tnpng
            
            self.run_on_fof_done = True
            
            
        def convert_emfs(self):
            # Spawn a thread to convert all the EMFs to PNGs
            def overwrite_output(filein,fileout):
                import hashlib
                with open(f, "rb") as file:
                    file_content = file.read()
                    hashed = hashlib.sha256(file_content).hexdigest()
                global converted_files
                if hashed not in converted_files:
                    notdone = True
                    nattempts=0
                    while notdone and nattempts<5:
                        try:
                            print('Starting export...',flush=True)
                            if os.path.exists(fileout):
                                os.remove(fileout)
                            args = [bfn,"--export-area-drawing","--export-background","#ffffff","--export-background-opacity",
                                "1.0","--export-dpi",str(300),"--export-filename",fileout,filein,]
                            dh.subprocess_repeat(args)
                            notdone = False
                            print('Finished export...',flush=True)
                        except:
                            nattempts+=1
                    if not os.path.exists(fileout): # write a 1x1 png
                        with open(fileout, 'wb') as f2:
                            f2.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82')
                    trigger_refresh()
                    converted_files[hashed] = fileout
                else:
                    import shutil
                    shutil.copy2(converted_files[hashed], fileout)


            from threading import Thread
            threads = []
            for ii, f in enumerate(self.files):
                if f.endswith('.emf'):
                    print('Making thumbnail '+self.thumbnails[ii],flush=True)
                    thread = Thread(target=overwrite_output, args=(f,self.thumbnails[ii]))
                    threads.append(thread)
                    while len([t for t in threads if t.is_alive()])>10:
                        time.sleep(0.1)
                    thread.start()
                        

        def run(self):
            print('Initial run',flush=True)
            self.run_on_fof()
            
            make_svg_display()       
            global myapp
            if myapp is None:
                myapp = True
                myapp = Make_Flask_App();
                time.sleep(1); # wait to see if check_for_refresh called 
                global openedgallery
                if not(openedgallery):
                    webbrowser.open("http://localhost:{}".format(str(PORTNUMBER)))
                    openedgallery = True;
            else:
                trigger_refresh()
            self.convert_emfs()    
            
            def get_modtimes():
                modtimes = dict()
                if os.path.isfile(self.fof):
                    modtimes[self.fof]  = os.path.getmtime(self.fof)
                elif os.path.isdir(self.fof):
                    fs = []
                    for f in os.scandir(self.fof):
                        if f.name.endswith(".svg") or f.name.endswith(".emf"):
                            fs.append(os.path.join(os.path.abspath(self.fof), f.name))
                    for f in fs:
                        modtimes[f] = os.path.getmtime(f);
                return modtimes
            
            lmts = get_modtimes();
            while not(self.stopped):
                time.sleep(1)
                mts = get_modtimes();
                if lmts!=mts:
                    print('Update '+self.fof,flush=True)
                    self.run_on_fof()
                    trigger_refresh()
                lmts = mts
            trigger_refresh()
            

    global myapp, converted_files, watcher_threads, openedgallery
    myapp = None
    converted_files = dict()
    lastupdate = time.time();
    watcher_threads = [];
    openedgallery = False;
        
    def process_selection(file,opened=True):
        if os.path.isdir(file) and os.path.isfile(os.path.join(file,'Gallery.cfg')):
            with open(os.path.join(file,'Gallery.cfg'), "r") as f:
                lines = f.readlines()
                lines = [line.strip() for line in lines]
                for ii, ln in enumerate(lines):
                    process_selection(os.path.join(file,ln),opened=(ii==0))
                return
        
        global watcher_threads
        for wt in watcher_threads:
            if file==wt.fof:
                wt.stopped = True
                watcher_threads.remove(wt);
        print('About to start')
        wt = WatcherThread(file,opened=opened)
        wt.win = win;
        watcher_threads.append(wt)
        wt.start()
      
    def quitnow():
        import requests
        requests.get('http://localhost:{}/stop'.format(str(PORTNUMBER)))  # kill Flask app
        
        for wt in watcher_threads:
            wt.stopped = True
        
        global temp_dir
        attempts = 0;
        while os.path.exists(temp_dir) and attempts<5:
            shutil.rmtree(temp_dir)
            attempts += 1
            time.sleep(5)
        
        pid = os.getpid()
        import signal
        os.kill(pid, signal.SIGINT) # or signal.SIGTERM
        
        
    if guitype=='gtk':            
        import gi
        gi.require_version('Gtk', '3.0')
        class GalleryViewerServer(Gtk.Window):
            def __init__(self):
                Gtk.Window.__init__(self, title="Gallery Viewer")
                self.set_default_size(400, -1)  # set width to 400 pixels, height can be automatic
                self.set_position(Gtk.WindowPosition.CENTER)
                
                
                self.containing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                self.containing_box.set_valign(Gtk.Align.CENTER)
                self.containing_box.set_margin_top(20)
                self.containing_box.set_margin_bottom(20)
        
                self.file_button = Gtk.Button(label="Add Powerpoint or Word file")
                self.file_button.connect("clicked", self.on_file_button_clicked)
                self.folder_button = Gtk.Button(label="Add folder")
                self.folder_button.connect("clicked", self.on_folder_button_clicked)
                self.clear_button = Gtk.Button(label="Clear selections")
                self.clear_button.connect("clicked", self.clear_clicked)
                self.gallery_button = Gtk.Button(label="Display gallery")
                self.gallery_button.connect("clicked", self.gallery_button_clicked)
                self.exit_button = Gtk.Button(label="Exit")
                self.exit_button.connect("clicked", self.on_button_clicked)
            
            
                # Create a list store to hold the file information
                self.liststore = Gtk.ListStore(str, str)
                self.treeview = Gtk.TreeView(model=self.liststore)
                renderer_text = Gtk.CellRendererText()
                column_text = Gtk.TreeViewColumn("Name", renderer_text, text=0)
                self.treeview.append_column(column_text)
                renderer_text = Gtk.CellRendererText()
                column_text = Gtk.TreeViewColumn("Location", renderer_text, text=1)
                self.treeview.append_column(column_text)
                self.scrolled_window_files = Gtk.ScrolledWindow()
                self.scrolled_window_files.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
                self.scrolled_window_files.set_size_request(600, 200)
                self.scrolled_window_files.set_vexpand(True)
                self.scrolled_window_files.add(self.treeview)

            
                        
                self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                # self.box.pack_start(self.containing_box, True, True, 0)
                self.box.pack_start(self.scrolled_window_files, True, True, 0)
                self.box.pack_start(self.file_button, False, False, 0)
                self.box.pack_start(self.folder_button, False, False, 0)
                self.box.pack_start(self.clear_button, False, False, 0)
                self.box.pack_start(self.gallery_button, False, False, 0)
                self.box.pack_start(self.exit_button, False, False, 0)
                self.add(self.box)
                
                
            def print_text(self, text):
                buffer = self.selected_file_label.get_buffer()
                start, end = buffer.get_bounds()
                if buffer.get_text(start, end, False)=='No file selected.':
                    buffer.set_text('')
                buffer.insert(buffer.get_end_iter(), text+'\n')
                end_iter = buffer.get_end_iter()
                buffer.move_mark(buffer.get_insert(), end_iter)
                self.selected_file_label.scroll_to_mark(buffer.get_insert(), 0, True, 0, 0)

            def on_button_clicked(self, widget):
                self.destroy()
                
            def on_file_button_clicked(self, widget):
                native = Gtk.FileChooserNative.new("Please choose a file", self, Gtk.FileChooserAction.OPEN, None, None)
                native.set_select_multiple(True)
                filter_ppt = Gtk.FileFilter()
                filter_ppt.set_name("Powerpoint or Word files")
                filter_ppt.add_pattern("*.docx")
                filter_ppt.add_pattern("*.pptx")
                native.add_filter(filter_ppt)
                response = native.run()
                if response == Gtk.ResponseType.ACCEPT:
                    selected_files = native.get_filenames()
                    for selected_file in selected_files:
                        file_name = os.path.basename(selected_file)
                        file_dir = os.path.dirname(selected_file)
                        self.liststore.append([file_name, file_dir])
                        process_selection(selected_file)
                native.destroy()
                
            def on_folder_button_clicked(self, widget):
                native = Gtk.FileChooserNative.new("Please choose a file or directory", self, Gtk.FileChooserAction.SELECT_FOLDER, None, None)
                response = native.run()
                if response == Gtk.ResponseType.ACCEPT:
                    selected_file = native.get_filename()
                    # self.print_text(selected_file)
                    
                    file_name = os.path.basename(selected_file)
                    file_dir = os.path.dirname(selected_file)
                    self.liststore.append([file_name, file_dir])
                    process_selection(selected_file)
                native.destroy()
                
            
            def gallery_button_clicked(self, widget):
                webbrowser.open("http://localhost:{}".format(str(PORTNUMBER)))
            def clear_clicked(self, widget):
                global watcher_threads
                for wt in reversed(watcher_threads):
                    wt.stopped = True
                    watcher_threads.remove(wt)
                self.liststore.clear()
                
        win = GalleryViewerServer()
        win.set_keep_above(True)
        # win.connect("destroy", quitnow)
        def quit_and_close(self):
            Gtk.main_quit();
            quitnow()
        win.connect("destroy", quit_and_close)
        win.show_all()
        win.set_keep_above(False)
        Gtk.main()
    elif guitype=='tkinter':
        root = tk.Tk()
        root.title("Gallery Viewer")
        root.attributes("-topmost", True)
        root.wm_minsize(width=350, height=-1)
        def open_file():
            file = filedialog.askopenfilename()
            file_label.config(text=file)
            process_selection(file)
        def end_program():
            print('Quitting')
            root.destroy()
            quitnow();
        file_label = tk.Label(root, text="No file selected.")
        file_label.pack()
        select_button = tk.Button(root, text="Select File", command=open_file)
        select_button.pack()
        end_button = tk.Button(root, text="End Program", command=end_program)
        end_button.pack()
        root.protocol("WM_DELETE_WINDOW", end_program)
        root.mainloop()

except:
    import traceback
    print("An error has occurred:")
    print(traceback.format_exc())
    import time
    time.sleep(10);