FROM python:3.10.8

ARG cobra_commit=99cbdf7fcb7709fcf0e4dc363d17a50ef0410ad7
ARG pyffi_commit=f767e0932bed93dfd528d416afca7927023fa42c
ARG nifxml_commit=9914a2b4984b4909cbc55512fa8162852b211565

WORKDIR /codegen
RUN git clone https://github.com/Candoran2/cobra-tools.git && cd cobra-tools && git reset --hard $cobra_commit && cd ..
RUN git clone https://github.com/DuncanWasHere/new-pyffi && cd new-pyffi && git reset --hard $pyffi_commit && cd .. && \
    mv ./new-pyffi/formats/nif ./cobra-tools/source/formats && \
    mv ./new-pyffi/spells ./cobra-tools/source && \
    mv ./new-pyffi/utils ./cobra-tools/source
RUN git clone https://github.com/Candoran2/nifxml.git && cd nifxml && git reset --hard $nifxml_commit && cd .. && \
    mv ./nifxml/nif.xml ./cobra-tools/source/formats/nif

WORKDIR cobra-tools
RUN python3 -m pip install --upgrade pip setuptools && \
    python3 -m pip install -r requirements.txt

ADD generate.sh .
CMD ["./generate.sh"]
