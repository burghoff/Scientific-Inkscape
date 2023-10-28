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
cmd = [pyexec, test_file]
process = subprocess.run(cmd, text=True, env=env)

env_vars_file = "env_vars.txt"
env = dict()
if os.path.exists(env_vars_file):
    with open(env_vars_file, "r") as f:
        env_line = f.readline()
        key, value = env_line.strip().split("=")
        env[key] = value
    os.remove(env_vars_file)

if 'TESTMAINVERSION' in os.environ:
    del os.environ['TESTMAINVERSION']