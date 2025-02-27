import os
import shutil
import json
import exceptions

import yaml
import tableschema
import jsonschema
import frontmatter
from functools import cached_property
from lxml import etree

import config

from table_schema_to_markdown import convert_source

import markdown
from markdown.treeprocessors import Treeprocessor
from markdown.extensions import Extension

import uuid

# First create the treeprocessor

class ImgExtractor(Treeprocessor):
    def run(self, doc):
        "Find all images and append to markdown.images. "
        self.markdown.images = []
        for image in doc.findall('.//img'):
            self.markdown.images.append(image.get('src'))

# Then tell markdown about it

class ImgExtExtension(Extension):
    def extendMarkdown(self, md, md_globals):
        img_ext = ImgExtractor(md)
        md.treeprocessors.add('imgext', img_ext, '>inline')

md = markdown.Markdown(extensions=[ImgExtExtension()])

if os.path.exists("./assets/") and os.path.isdir("./assets/"):
    shutil.rmtree("./assets/")

class BaseValidator(object):
    CHANGELOG_FILENAME = "CHANGELOG.md"
    CONSOLIDATION_FILENAME = "consolidation.yml"

    def __init__(self, repo):
        super(BaseValidator, self).__init__()
        self.repo = repo
        self.git_repo = repo.git_repo

    @property
    def data_dir(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        return os.path.join(current_dir, "data")

    @property
    def asset_dir(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        return os.path.join(current_dir, "assets")

    @property
    def static_dir(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        return os.path.join(current_dir, "static")

    @property
    def target_dir(self):
        return os.path.join(self.data_dir, self.repo.slug, self.repo.current_version)

    @property
    def target_latest_dir(self):
        return os.path.join(self.data_dir, self.repo.slug, "latest")

    def validate(self):
        self.check_file_exists("README.md")

    def extract(self):
        raise NotImplementedError

    def metadata(self):
        slug = self.repo.slug

        return {
            "slug": slug,
            "title": self.title,
            "description": self.description,
            "homepage": self.homepage,
            "type": self.repo.schema_type,
            "consolidation": self.consolidation_data(slug),
            "email": self.repo.email,
            "external_doc":self.repo.external_doc,
            "external_tool":self.repo.external_tool,
            "version": self.repo.current_version,
            "has_changelog": self.has_changelog,
            "schemas": self.schemas_metadata(),
        }

    def schema_url(self, path):
        return f"{config.BASE_DOMAIN}/schemas/{self.repo.slug}/{self.repo.current_version}/{path}"

    def consolidation_data(self, slug):
        with open(os.path.join(self.static_dir, self.CONSOLIDATION_FILENAME)) as f:
            return yaml.safe_load(f).get(slug, None)

    def change_images_link(self, content,assetnewnames):
        html = md.convert(content)
        for img in md.images:
            ext = os.path.splitext(img)[1]
            filename = os.path.basename(img)
            new_filename = filename.split(ext)[0]
            if filename in assetnewnames:
                new_filename = assetnewnames[filename]
            if(img.startswith('./assets/')):
                content = content.replace('(./assets/'+filename+')','(/assets/images/'+new_filename+ext+')')
            if(img.startswith('assets/')):
                content = content.replace('(assets/'+filename+')','(/assets/images/'+new_filename+ext+')')
        html = md.convert(content)
        return content

    def move_assets(self,assetfiles,assetnewnames):
        if not os.path.exists(self.asset_dir):
            os.makedirs(self.asset_dir)

        for asset in assetfiles:
            for assetnewname in assetnewnames:
                if(asset == assetnewname):
                    ext = os.path.splitext(asset)[1]
                    shutil.copyfile(assetfiles[asset], self.asset_dir+"/"+assetnewnames[assetnewname]+ext)

    def move_files(self, files, assetnewnames={}):
        if not os.path.exists(self.target_dir):
            os.makedirs(self.target_dir)

        if not os.path.exists(self.target_latest_dir):
            os.makedirs(self.target_latest_dir)

        for filename, src_filepath in files.items():
            if src_filepath is None:
                continue
            front_matter = self.front_matter_for(filename)
            # Add YAML front matter if required
            if front_matter is not None:
                content = frontmatter.dumps(
                    frontmatter.load(src_filepath, **front_matter)
                )
                content = self.change_images_link(content,assetnewnames)
                with open(self.target_filepath(filename), "w") as f:
                    f.write(content)
            else:
                shutil.copyfile(src_filepath, self.target_filepath(filename))

        # Always copy schema to latest directory since versions
        # are sorted
        for schema in self.schemas_metadata():
            shutil.copyfile(
                self.filepath(schema["original_path"]),
                self.target_latest_filepath(schema["path"]),
            )

    def check_file_exists(self, filename):
        if not os.path.isfile(self.filepath(filename)):
            message = "Required file %s was not found" % filename
            raise exceptions.MissingFileException(self.repo, message)

    def filepath_or_none(self, filename):
        if not os.path.isfile(self.filepath(filename)):
            return None

        return self.filepath(filename)

    def target_filepath(self, filename):
        return os.path.join(self.target_dir, filename)

    def target_latest_filepath(self, filename):
        return os.path.join(self.target_latest_dir, filename)

    def filepath(self, filename):
        return os.path.join(self.git_repo.working_dir, filename)

    def front_matter_for(self, filename):
        version = self.repo.current_version
        slug = self.repo.slug

        if filename == "README.md":
            if self.is_latest_version():
                permalink = "/%s/%s.html" % (slug, "latest")
                redirect_from = "/%s/%s.html" % (slug, version)
            else:
                permalink = "/%s/%s.html" % (slug, version)
                redirect_from = None

            return {
                "permalink": permalink,
                "title": self.title,
                "version": version,
                "redirect_from": redirect_from,
            }
        if filename == "documentation.md":
            if self.is_latest_version():
                permalink = "/%s/%s/documentation.html" % (slug, "latest")
                redirect_from = "/%s/%s/documentation.html" % (slug, version)
            else:
                permalink = "/%s/%s/documentation.html" % (slug, version)
                redirect_from = None

            return {
                "permalink": permalink,
                "title": "Documentation de " + self.title,
                "version": version,
                "redirect_from": redirect_from,
            }
        if filename == self.CHANGELOG_FILENAME:
            if not self.is_latest_version():
                raise ValueError
            self.has_changelog = True
            permalink = "/%s/%s/changelog.html" % (slug, "latest")
            redirect_from = "/%s/%s/changelog.html" % (slug, version)

            return {
                "permalink": permalink,
                "title": "CHANGELOG de " + self.title,
                "version": version,
                "redirect_from": redirect_from,
            }
        if filename.endswith(".md"):
            if self.is_latest_version():
                permalink = "/%s/%s/%s.html" % (slug, "latest",os.path.splitext(filename)[0])
                redirect_from = "/%s/%s/%s.html" % (slug, version,os.path.splitext(filename)[0])
            else:
                permalink = "/%s/%s/%s.html" % (slug, version,os.path.splitext(filename)[0])
                redirect_from = None

            return {
                "permalink": permalink,
                "title": "Documentation de " + self.title + " : propriété " + os.path.splitext(filename)[0],
                "version": version,
                "redirect_from": redirect_from,
            }

        return None

    def is_latest_version(self):
        return self.repo.current_tag == self.repo.latest_valid_tag()


class XsdSchemaValidator(BaseValidator):
    def __init__(self, repo):
        super(XsdSchemaValidator, self).__init__(repo)
        self.has_changelog = False
        self.title = None
        self.description = None
        self.homepage = None
        self.schemas_config = None

    def schemas_metadata(self):
        res = []
        for schema in self.schemas_config:
            path = os.path.basename(schema["path"])

            res.append(
                {
                    "path": path,
                    "original_path": schema["path"],
                    "title": schema["title"],
                    "latest_url": self.schema_url(path),
                }
            )

        return res

    def validate(self):
        super(XsdSchemaValidator, self).validate()
        self.check_file_exists("schemas.yml")

        try:
            with open(self.filepath("schemas.yml"), "r") as f:
                config = yaml.safe_load(f)
                self.schemas_config = config["schemas"]
                self.title = config["title"]
                self.description = config["description"]
                self.homepage = config["homepage"]
                for schema in config["schemas"]:
                    self.check_schema(schema["path"], schema["title"])
        except Exception as e:
            message = "`schemas.yml` has not the required format: " + repr(e)
            raise exceptions.InvalidSchemaException(self.repo, message)

    def check_schema(self, path, title):
        try:
            etree.XMLSchema(etree.parse(self.filepath(path)))
        except Exception as e:
            message = "XSD schema %s at `%s` is not valid. Errors: %s" % (
                title,
                path,
                repr(e),
            )
            raise exceptions.InvalidSchemaException(self.repo, message)

    def extract(self):
        files = {
            "README.md": self.filepath_or_none("README.md"),
            "SEE_ALSO.md": self.filepath_or_none("SEE_ALSO.md"),
            "CONTEXT.md": self.filepath_or_none("CONTEXT.md"),
        }

        for schema in self.schemas_metadata():
            files[schema["path"]] = self.filepath(schema["original_path"])

        if self.is_latest_version():
            changelog_path = self.filepath_or_none(self.CHANGELOG_FILENAME)
            files[self.CHANGELOG_FILENAME] = changelog_path
            self.has_changelog = changelog_path is not None

        self.move_files(files)


class JsonSchemaValidator(XsdSchemaValidator):
    def __init__(self, repo):
        super(JsonSchemaValidator, self).__init__(repo)

    def check_schema(self, path, title):
        try:
            with open(self.filepath(path)) as f:
                schema_data = json.load(f)
            validator = jsonschema.validators.validator_for(schema_data)
            validator.check_schema(schema_data)
        except Exception as e:
            message = "JSON Schema %s at `%s` is not valid. Errors: %s" % (
                title,
                path,
                repr(e),
            )
            raise exceptions.InvalidSchemaException(self.repo, message)


class TableSchemaValidator(BaseValidator):
    SCHEMA_FILENAME = "schema.json"

    def __init__(self, repo):
        super(TableSchemaValidator, self).__init__(repo)
        self.schema_data = None
        self.has_changelog = False

    def schemas_metadata(self):
        return [
            {
                "path": self.SCHEMA_FILENAME,
                "original_path": self.SCHEMA_FILENAME,
                "title": self.title,
                "latest_url": self.schema_url(self.SCHEMA_FILENAME),
            }
        ]

    @property
    def title(self):
        return self.schema_json_data()["title"]

    @property
    def description(self):
        return self.schema_json_data()["description"]

    @property
    def homepage(self):
        return self.schema_json_data()["homepage"]

    def validate(self):
        super(TableSchemaValidator, self).validate()
        self.check_file_exists(self.SCHEMA_FILENAME)
        self.check_schema(self.SCHEMA_FILENAME)
        self.check_extra_keys()

    def extract(self):
        links = []
        documentationfiles = {}
        assetfiles = {}
        assetnewnames = {}
        if(os.path.isdir(self.filepath("documentation/"))):
            if(os.path.isdir(self.filepath("documentation/assets/"))):
                for filename in os.listdir(self.filepath("documentation/assets/")):
                    assetnewnames = {**assetnewnames, **{filename: str(uuid.uuid1())}}
                    assetfiles = {**assetfiles, **{filename: self.filepath("documentation/assets/"+filename)}}

            for filename in os.listdir(self.filepath("documentation/")):
                if filename.endswith(".md"):
                    links.append(os.path.splitext(filename)[0].lower())
                    documentationfiles = {**documentationfiles, **{filename: self.filepath("documentation/")+filename}}


        with open(self.filepath("documentation.md"), "w") as out:
            convert_source(self.filepath(self.SCHEMA_FILENAME), out, 'page',links)

        files = {
            self.SCHEMA_FILENAME: self.filepath_or_none(self.SCHEMA_FILENAME),
            "README.md": self.filepath_or_none("README.md"),
            "SEE_ALSO.md": self.filepath_or_none("SEE_ALSO.md"),
            "CONTEXT.md": self.filepath_or_none("CONTEXT.md"),
            "documentation.md": self.filepath("documentation.md"),
        }

        files = {**files, **documentationfiles}

        if self.is_latest_version():
            files[self.CHANGELOG_FILENAME] = self.filepath_or_none(
                self.CHANGELOG_FILENAME
            )

        self.move_files(files,assetnewnames)
        self.move_assets(assetfiles,assetnewnames)

    def check_extra_keys(self):
        keys = ["title", "description", "homepage", "version"]
        for key in [k for k in keys if k not in self.schema_json_data()]:
            message = "Key `%s` is a required key and is missing from %s" % (
                key,
                self.SCHEMA_FILENAME,
            )
            raise exceptions.InvalidSchemaException(self.repo, message)

    def check_schema(self, filename):
        try:
            tableschema.validate(self.filepath(filename))
        except tableschema.exceptions.ValidationError as e:
            errors = "; ".join([repr(e) for e in e.errors])
            message = "Schema %s is not a valid TableSchema schema. Errors: %s" % (
                filename,
                errors,
            )
            raise exceptions.InvalidSchemaException(self.repo, message)
        except:
            message = "Schema %s is not a valid TableSchema schema." % (
                filename
            )
            raise exceptions.InvalidSchemaException(self.repo, message)

    def schema_json_data(self):
        if self.schema_data is not None:
            return self.schema_data

        with open(self.filepath(self.SCHEMA_FILENAME)) as f:
            self.schema_data = json.load(f)
        return self.schema_data


class GenericValidator(BaseValidator):
    SCHEMA_FILENAME = "schema.yml"

    def __init__(self, repo):
        super().__init__(repo)
        self.has_changelog = False

    def schemas_metadata(self):
        return [
            {
                "path": self.SCHEMA_FILENAME,
                "original_path": self.SCHEMA_FILENAME,
                "title": self.title,
                "latest_url": self.schema_url(self.SCHEMA_FILENAME),
            }
        ]

    @property
    def title(self):
        return self.schema_data["title"]

    @property
    def description(self):
        return self.schema_data["description"]

    @property
    def homepage(self):
        return self.schema_data["homepage"]

    def validate(self):
        super().validate()
        # order matters!
        self.check_file_exists(self.SCHEMA_FILENAME)
        self.check_schema(self.SCHEMA_FILENAME)
        self.check_extra_keys()

    def extract(self):
        files = {
            self.SCHEMA_FILENAME: self.filepath(self.SCHEMA_FILENAME),
            "README.md": self.filepath_or_none("README.md"),
            "SEE_ALSO.md": self.filepath_or_none("SEE_ALSO.md"),
            "CONTEXT.md": self.filepath_or_none("CONTEXT.md"),
        }

        if self.is_latest_version():
            changelog_path = self.filepath_or_none(self.CHANGELOG_FILENAME)
            files[self.CHANGELOG_FILENAME] = changelog_path
            self.has_changelog = changelog_path is not None

        self.move_files(files)

    def check_extra_keys(self):
        keys = ["title", "description", "homepage", "version"]
        for key in [k for k in keys if k not in self.schema_data]:
            message = "Key `%s` is a required key and is missing from %s" % (
                key,
                self.SCHEMA_FILENAME,
            )
            raise exceptions.InvalidSchemaException(self.repo, message)

    def check_schema(self, filename):
        try:
            _ = self.schema_data
        except yaml.error.YAMLError as e:
            message = "Yaml file not valid. Error: %s" % (
                repr(e),
            )
            raise exceptions.InvalidSchemaException(self.repo, message)

    @cached_property
    def schema_data(self):
        with open(self.filepath(self.SCHEMA_FILENAME)) as f:
            return yaml.safe_load(f) or {}
