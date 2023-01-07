import subprocess, os

test_versions = ['1.0','1.1','1.2.2','1.3']

for version in test_versions:
  # Set the environment variable
  env = dict(os.environ)
  env['TESTMAINVERSION'] = version

  # Call pytest and capture the output
  result = subprocess.run(['pytest', 'test_main.py'], stdout=subprocess.PIPE, env=env)

  # Split the output into lines
  lines = result.stdout.decode('utf-8').split('\n')

  # Print the lines that start with 'test_main.py'
  for line in lines:
    if line.startswith('test_main.py'):
        pline = line.strip('test_main.py')
        pversion = version + ' '*(6-len(version))
        print(pversion + ':' + pline)

# Delete the environment variable
if 'TESTMAINVERSION' in os.environ:
    del os.environ['TESTMAINVERSION']
