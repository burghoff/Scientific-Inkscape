import subprocess, os
from test_main import vpaths, version
vpy = dict()
for k, v in vpaths.items():
    b = os.path.join(v,'bin')
    f = os.path.join(b, 'python.exe');
    if os.path.exists(f):
        vpy[k] = f
pyexec = vpy[version]


# Set the environment variable
env = dict(os.environ)
env['TESTMAINVERSION'] = version

test_file = "test_main.py"
cmd = [pyexec, "-m", "pytest", test_file]
process = subprocess.run(cmd, text=True, env=env)

if 'TESTMAINVERSION' in os.environ:
    del os.environ['TESTMAINVERSION']