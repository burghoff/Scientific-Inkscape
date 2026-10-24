import subprocess, os, time
from test_main import vpaths
vpy = dict()
for k, v in vpaths.items():
    b = os.path.join(v,'bin')
    f = os.path.join(b, 'python.exe');
    if os.path.exists(f):
        vpy[k] = f


# Set column widths for Version and Pango columns
version_col_width = 7
pango_col_width = 6

# Print table headers
header = f"{ 'Version'.ljust(version_col_width)} :{ ' Pango'.ljust(pango_col_width)} :{ ' Results'}"
print(header)
print("-" * len(header))

for version, pyexec in vpy.items():
    # Set the environment variable
    env = dict(os.environ)
    env['TESTMAINVERSION'] = version
    # Don't leak the parent's version-specific SI_FC_DIR (set at test_main import
    # for the file's default version) into every subprocess -- it forces the wrong
    # fontconfig/freetype and breaks Pango detection. Each subprocess sets its own.
    env.pop('SI_FC_DIR', None)

    test_file = "test_main.py"
    cmd = [pyexec, "-m", "pytest", test_file]
    
    tic = time.time()
    process = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, text=True, env=env, shell=True)
    stdout, stderr = process.communicate()
    process.wait()
    toc = time.time()-tic
    
    env_vars_file = "env_vars.txt"
    env = dict()
    if os.path.exists(env_vars_file):
        with open(env_vars_file, "r") as f:
            for env_line in f:
                key, value = env_line.strip().split("=")
                env[key] = value
        os.remove(env_vars_file)
    
    lines = stdout.split('\n')

    pversion = version.ljust(version_col_width)
    pango_info = f"{'Yes' if env.get('HASPANGO', 'N/A') == 'True' else 'No'}".ljust(pango_col_width - 1)
    printed = False
    for line in lines:
        if line.endswith('%]'):
            if line.startswith('test_main.py '):
                pline = line[len('test_main.py '):]
            else:
                pline = line
            print(f"{pversion} : {pango_info} : {pline}")
            printed = True
    if not printed:
        # No pytest progress line means the run crashed/was killed before finishing
        # (a soft test failure still prints one). Surface it instead of dropping the row.
        tail = next((l for l in reversed(lines) if l.strip()), '')
        print(f"{pversion} : {pango_info} : CRASHED (rc={process.returncode}, no summary) {tail[:60]}")

# Delete the environment variable
if 'TESTMAINVERSION' in os.environ:
    del os.environ['TESTMAINVERSION']
