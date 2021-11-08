# Inkscape Auto-Exporter, by David Burghoff
# Service that checks a folder for changes in svg files, and then exports them 
# automatically to another folder in multiple formats.

PNG_DPI = 600;                                  # resolution for PNG export
BASE_TIMEOUT = 60; 
MAX_ATTEMPTS = 4;


import sys, platform, subprocess, os, threading, datetime
# Load the configuration
import pickle
mypath = os.path.dirname(os.path.realpath(sys.argv[0]));
f=open(os.path.join(mypath,'ae_settings.p'),'rb');
s=pickle.load(f); f.close(); os.remove(os.path.join(mypath,'ae_settings.p'));
watchdir = s[0]; writedir = s[1]; bfn = s[2]; fmts= s[3];
sys.path += s[4];

islinux = (platform.system().lower()=='linux')
if not(islinux):
    import tkinter
    from tkinter import filedialog
    promptstring = 'Enter D to change watch/write directories, A to export all now, and Q to quit: '
else:
    promptstring = 'Enter A to export all now and Q to quit: '

fmts = [(v.lower()=='true') for v in fmts.split('_')];
exp_fmts = []
if fmts[0]: exp_fmts.append('pdf')
if fmts[1]: exp_fmts.append('png')
if fmts[2]: exp_fmts.append('emf')
if fmts[3]: exp_fmts.append('eps')
       

if platform.system().lower()=='darwin': print(' ')
print('Scientific Inkscape Autoexporter')
print('\nPython interpreter: '+sys.executable)
print('Inkscape binary: '+bfn+'\n')
# Use the Inkscape binary to export the file
def export_file(bfn,fin,fout,fformat,timeoutv):
    myoutput = fout[0:-4] + '.' + fformat
    callstr = '"'+bfn+'"'+' --export-background=#ffffff --export-background-opacity=1.0 --export-dpi='\
            +str(PNG_DPI)+' --export-filename=' + '"'+myoutput+'"' + ' "'+fin+'"'
    print('    To '+fformat+'...',end=' ',flush=True)
    try:
#        arg2 = command.to_args(command.which('inkscape.exe'), export_background='#ffffff',\
#                               export_background_opacity=1.0,export_dpi=PNG_DPI,export_filename=myoutput);
#        print(arg2)
        arg2 = [bfn, '--export-background','#ffffff','--export-background-opacity','1.0','--export-dpi',\
                                str(PNG_DPI),'--export-filename',myoutput,fin]
        p=subprocess.run(arg2, shell=False,timeout=timeoutv,stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
#        command.inkscape(fin,export_background='#ffffff',export_background_opacity=1.0,export_dpi=PNG_DPI,\
#                             export_filename=myoutput) # doesn't work on macOS
        print('done!'); return True
    except subprocess.TimeoutExpired:
        print('timed out after '+str(timeoutv)+' seconds'); return False
        

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
#    Write_Config(bfn,None,None)
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
#    Write_Config(None,watchdir,writedir)
    return watchdir,writedir
        
# Convenience functions
def joinmod(dirc,f):
    return os.path.join(os.path.abspath(dirc),f)
def timenow():
    return datetime.datetime.now().timestamp();

# Get svg files in all subdirectories
def get_files(dirin,direxclude):
    fs = []
    # for d in os.walk(dirin):
    #     if direxclude is None or not(os.path.abspath(d[0])==os.path.abspath(direxclude)):
    #         for f in d[2]:
    #             if f[-4:]=='.svg':
    #                 fs.append(os.path.join(os.path.abspath(d[0]),f))
    for f in os.scandir(dirin):
        if f.name[-4:]=='.svg':
            fs.append(os.path.join(os.path.abspath(dirin),f.name))
    return fs

# Threading class
class myThread(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.stopped = False
        self.ui = None  # user input
        self.nf = True;  # new folder
        self.ea = False; # export all
        self.dm = False; # debug mode
    def run(self):
        if self.threadID==1:
        # Main thread
            ltm = timenow();
            while not(self.stopped):
                if self.nf:
#                    print('Inkscape binary: '+self.bfn)
                    print('Export formats: '+', '.join([v.upper() for v in exp_fmts]))
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
                    
                    loopme = True; 
                    while loopme:
                        for f in updatefiles:
                            # while not(self.stopped):
                            print('\nExporting '+f+'')
                            for fmt in exp_fmts:
                                finished = False;
                                natt = 0;
                                while not(finished) and not(self.stopped) and natt<MAX_ATTEMPTS:
                                    natt+=1;
                                    finished = export_file(self.bfn,f,joinmod(self.writedir,os.path.split(f)[1]),fmt,BASE_TIMEOUT*natt);
                        loopme = (len(updatefiles)>0 and self.dm);
                    if len(updatefiles)>0:
                        print(promptstring)

        if self.threadID==2:
            self.ui = input(promptstring)
    def stop(self):
         self.stopped = True;

# Main loop
t1 = myThread(1);
t1.bfn = bfn;
t1.watchdir = watchdir;
t1.writedir = writedir;
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
            if not(islinux):
                t1.watchdir, t1.writedir = Get_Directories()
                t1.nf = True
            t2 = myThread(2); t2.start();
        elif t2.ui in ['A','a']:
            t1.ea = True;
            t2 = myThread(2); t2.start();
        elif t2.ui in ['#']:
            t1.dm = True; # entering # starts an infinite export loop in the current dir
            t1.ea = True;
            t2 = myThread(2); t2.start();
        else:
            print('Invalid input!')
            t2 = myThread(2); t2.start();

# On macOS close the terminal we opened
# https://superuser.com/questions/158375/how-do-i-close-the-terminal-in-osx-from-the-command-line
if platform.system().lower()=='darwin':
   os.system('osascript -e \'tell application \"Terminal\" to close first window\' & exit');