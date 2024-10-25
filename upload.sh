rsync -avP --delete ./src/ aicloud:~/pub-summarizer/src --exclude "*.pyc"
rsync -avP ./requirements.txt aicloud:~/pub-summarizer/
rsync -avP ./config.yaml aicloud:~/pub-summarizer/
rsync -avP ./pubsum.def aicloud:~/pub-summarizer/