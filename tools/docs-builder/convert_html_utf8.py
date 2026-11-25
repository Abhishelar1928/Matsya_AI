import codecs

content = codecs.open('scratch/text_data_home.html', 'r', 'utf-16le').read()
with codecs.open('scratch/text_data_home_utf8.html', 'w', 'utf-8') as f:
    f.write(content)
