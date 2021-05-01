# Inkscape Auto-Exporter, by David Burghoff
# Daemon that checks a folder for changes in svg files, and then exports them 
# automatically to another folder in multiple formats

EXPORT_FORMATS = ['pdf','emf','png']            # list of formats to use
PNG_DPI = 600;                                  # resolution for PNG export

# Any more options, and you will need to modify the call string (see export_file function below) 

import tkinter
from tkinter import filedialog
import subprocess, os
import datetime
import threading
import platform

# Use the Inkscape binary to export the file
def export_file(bfn,fin,fout,fformat,timeoutv):
    myoutput = fout[0:-4] + '.' + fformat
    if fformat=='png':
        callstr = '"'+bfn+'"'+' --export-background=#ffffff --export-background-opacity=1.0 --export-dpi='\
                +str(PNG_DPI)+' --export-filename=' + '"'+myoutput+'"' + ' "'+fin+'"'
    else:
        callstr = '"'+bfn+'"'+' --export-filename=' + '"'+myoutput+'"' + ' "'+fin+'"'
    print('    To '+fformat+'...',end='')
    try:
        subprocess.run(callstr, shell=True,timeout=timeoutv,stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print('done!'); return True
    except subprocess.TimeoutExpired:
        print('timed out after '+str(timeoutv)+' seconds'); return False
        

# Read and write to config file
def Read_Config():
    try:
        f = open('Inkscape_AutoExporter.cfg', 'r')
        cfg = f.read(); f.close();
        cfg = cfg.split('\n');
        for ii in range(len(cfg)):
            if cfg[ii]=='None':
                cfg[ii]=None
        while len(cfg)<3:
            cfg.append(None)
        return cfg[0],cfg[1],cfg[2]
    except:
        return None, None, None
def Write_Config(bfn,watchdir,writedir):
    if bfn is None or watchdir is None or writedir is None:
        bfn2, watchdir2, writedir2 = Read_Config();
    if bfn is None:         bfn      = bfn2;
    if watchdir is None:    watchdir = watchdir2;
    if writedir is None:    writedir = writedir2;
    writestr = '\n'.join([str(bfn),str(watchdir),str(writedir)])
    f = open('Inkscape_AutoExporter.cfg', 'w')
    f.write(writestr); f.close();

# Get a valid binary file location and validate that it's actually Inkscape
def Validate_Binary(bfn):
    if bfn==None: # check OS default locations
        if platform.system()=='Windows':
            try:
                bfn = os.path.join(os.environ['ProgramW6432'],'Inkscape','bin','inkscape.exe');
            except:
                pass
        elif platform.system()=='Darwin':
            bfn = "/Applications/Inkscape.app/Contents/MacOS/inkscape"
    goodbinfile = False
    while not(goodbinfile):
        if os.path.exists(bfn):
            try:
                tProc = subprocess.run('"'+bfn+'"'+' --help', stdout=subprocess.PIPE, shell=True)
                tFStR = tProc.stdout
                goodbinfile = 'Inkscape' in str(tFStR)
            except:
                pass
        if not(goodbinfile):
            try:
                root = tkinter.Tk(); root.geometry("1x1"); root.lift(); root.overrideredirect(1);
                print('Locate the Inkscape binary');
                bfn = tkinter.filedialog.askopenfilename(title='Locate the Inkscape binary');
                root.destroy(); 
            except:
                pass
    if bfn=='':
        print('Cancelled!'); raise
    Write_Config(bfn,None,None)
    return bfn

def Get_Directories():
    root = tkinter.Tk(); root.geometry("1x1"); root.lift(); root.overrideredirect(1); 
    print('Select a directory to watch (includes subdirectories)');
    watchdir = tkinter.filedialog.askdirectory(title='Select a directory to watch (includes subdirectories)'); root.destroy(); 
    if watchdir=='':
        print('Cancelled!'); raise     
    root = tkinter.Tk(); root.geometry("1x1"); root.lift(); root.overrideredirect(1); 
    print('Select a directory to write to');
    writedir = tkinter.filedialog.askdirectory(title='Select a directory to write to'); root.destroy();
    if writedir=='':
        print('Cancelled!'); raise
    Write_Config(None,watchdir,writedir)
    return watchdir,writedir
        
# Convenience functions
def joinmod(dirc,f):
    return os.path.join(os.path.abspath(dirc),f)
def timenow():
    return datetime.datetime.now().timestamp();

# Get svg files in all subdirectories
def get_files(dirin,direxclude):
    fs = []
    for d in os.walk(dirin):
        if direxclude is None or not(os.path.abspath(d[0])==os.path.abspath(direxclude)):
            for f in d[2]:
                if f[-4:]=='.svg':
                    fs.append(os.path.join(os.path.abspath(d[0]),f))
    return fs

# Threading class
class myThread(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.stopped = False
        self.ui = None
        self.nf = True;
        self.ea = False;
    def run(self):
        if self.threadID==1:
        # Main thread
            ltm = timenow();
            while not(self.stopped):
                if self.nf:
                    print('Inkscape binary: '+self.bfn)
                    print('Watch directory: '+self.watchdir)
                    print('Write directory: '+self.writedir)
                    files = get_files(self.watchdir,None);
                    lastmod = [os.path.getmtime(f) for f in files]
                    self.nf = False
                if timenow()>ltm + 0.25:
                    ltm = timenow();
                    # newfiles = [fn for fn in os.listdir(watchdir) if fn[-3:]=='svg']
                    newfiles = get_files(self.watchdir,None);
                    newlastmod = [0 for f in newfiles]
                    for ii in range(len(newfiles)):
                        try:
                            newlastmod[ii] = os.path.getmtime(newfiles[ii])
                        except FileNotFoundError:     
                            newlastmod[ii] = lastmod[ii]
                    
                    updatefiles = [];
                    if any([not(f in newfiles) for f in files]):
                        pass; # deleted files; 
                    elif any([not(n in files) for n in newfiles]):
                        updatefiles += [n for n in newfiles if not(n in files)]; # new files
                    elif any([newlastmod[ii]>lastmod[ii]+1 for ii in range(len(files))]): #updated files
                        updatefiles += [newfiles[ii] for ii in range(len(files)) if not(lastmod[ii]==newlastmod[ii])];
                    files = newfiles
                    lastmod = newlastmod
                    
                    if self.ea:  # export all
                        self.ea = False;
                        updatefiles = files
                    
                    for f in updatefiles:
                        # while not(self.stopped):
                        print('\nExporting '+f+'')
                        for fmt in EXPORT_FORMATS:
                            finished = False;
                            natt = 0;
                            while not(finished) and not(self.stopped) and natt<4:
                                BASE_TIMEOUT = 15; natt+=1;
                                finished = export_file(self.bfn,f,joinmod(self.writedir,os.path.split(f)[1]),fmt,BASE_TIMEOUT*natt);

        if self.threadID==2:
            self.ui = input('Enter D to change watch/write directories, B to change Inkscape binary, A to export all, and Q to quit: ')
    def stop(self):
         self.stopped = True;

# Main loop
t1 = myThread(1);
t1.bfn, t1.watchdir, t1.writedir = Read_Config();
t1.bfn = Validate_Binary(t1.bfn);
if t1.watchdir is None or t1.writedir is None:
    t1.watchdir, t1.writedir = Get_Directories()
           
t1.start();
while t1.nf:  # wait until it's done initializing
    pass
t2 = myThread(2); t2.start();
keeprunning = True;
while keeprunning:
    if not(t2.is_alive()):
        if t2.ui in ['Q','q']:
            t1.stop();
            keeprunning = False
        elif t2.ui in ['D','d']:
            t1.watchdir, t1.writedir = Get_Directories()
            t1.nf = True
            t2 = myThread(2); t2.start();
        elif t2.ui in ['B','b']:
            t1.bfn = Validate_Binary(0)
            t1.nf = True
            t2 = myThread(2); t2.start();
        elif t2.ui in ['A','a']:
            t1.ea = True;
            t2 = myThread(2); t2.start();
        else:
            print('Invalid input!')
            t2 = myThread(2); t2.start();