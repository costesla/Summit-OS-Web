import os
print(f"CWD: {os.getcwd()}")
print(f"Contents: {os.listdir('.')}")
if os.path.exists('backend'):
    print("Backend dir exists")
    print(f"Backend contents: {os.listdir('backend')}")
    
    with open('test_write.txt', 'w') as f:
        f.write('test')
    print("Wrote test_write.txt")
else:
    print("Backend dir NOT found")
