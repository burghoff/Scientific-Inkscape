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
    
    for line in lines:
        if line.startswith('test_main.py'):
            pline = line.strip('test_main.py')
            pversion = version.ljust(version_col_width)
            pango_info = f"{'Yes' if env.get('HASPANGO', 'N/A') == 'True' else 'No'}".ljust(pango_col_width - 1)
            print(f"{pversion} : {pango_info} :{pline}")

# Delete the environment variable
if 'TESTMAINVERSION' in os.environ:
    del os.environ['TESTMAINVERSION']
