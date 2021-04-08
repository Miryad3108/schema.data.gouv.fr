FROM python:3.9

RUN \
  apt-get update && \
  apt-get install -y ruby-full

COPY ./aggregateur /aggregateur
COPY ./api /api
COPY ./web /web

RUN ls -la

WORKDIR /aggregateur

RUN python -m venv venv 
RUN . venv/bin/activate
RUN pip install -r requirements.txt

RUN apt-get install -y locales

RUN echo "fr_FR.UTF-8 UTF-8" | tee -a /etc/locale.gen
RUN locale-gen

ARG CACHEBUST=1
RUN mkdir -p repos

ARG CACHEBUST=1
RUN rm -rf data

RUN python --version

ARG CACHEBUST=1
RUN python main.py

RUN wget -O /tmp/schema-catalog.json https://opendataschema.frama.io/catalog/schema-catalog.json
RUN jsonschema /tmp/schema-catalog.json -i data/schemas.json

ARG CACHEBUST=1
RUN python issues.py

WORKDIR /api
RUN python -m venv venv
RUN . venv/bin/activate
RUN pip install -r requirements.txt
RUN mkdir api

ARG CACHEBUST=1
RUN python recommendations.py > api/recommendations.json

RUN apt-get install -y nodejs \
    npm
RUN npm install npm@latest -g
RUN gem install bundler -v 1.17.2

EXPOSE 80
RUN apt-get install -y nginx
RUN rm -v /etc/nginx/nginx.conf
ADD nginx.conf /etc/nginx/

RUN adduser rubyapp

RUN chown -R rubyapp:rubyapp /web
RUN chown -R rubyapp:rubyapp /aggregateur
RUN chown -R rubyapp:rubyapp /api

USER rubyapp

WORKDIR /web
RUN npm install

ARG CACHEBUST=1
RUN bundle install --path vendor/bundle
ARG CACHEBUST=1
RUN ./build-local.sh

USER root

ARG CACHEBUST=1
RUN cp -r /web/_site/* /usr/share/nginx/html/
ARG CACHEBUST=1
RUN cp -r /web/_site/* /var/www/html/

# Append "daemon off;" to the beginning of the configuration
RUN echo "daemon off;" >> /etc/nginx/nginx.conf

CMD service nginx start
