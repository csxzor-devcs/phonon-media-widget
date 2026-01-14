from PIL import Image
img = Image.open("icon.png")
img.save("icon.ico", format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("Converted icon.png to icon.ico")
