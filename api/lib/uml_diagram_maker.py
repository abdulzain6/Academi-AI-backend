from __future__ import print_function
import base64
import logging
import string
import httplib2
import six
from zlib import compress
from six.moves.urllib.parse import urlencode
from langchain.chat_models.base import BaseChatModel
if six.PY2:
    from string import maketrans
else:
    maketrans = bytes.maketrans
from langchain.chains import LLMChain
from pydantic import BaseModel, Field
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
    
plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
base64_alphabet   = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
b64_to_plantuml = maketrans(base64_alphabet.encode('utf-8'), plantuml_alphabet.encode('utf-8'))



class PlantUMLHTTPError(Exception):
    """
    Request to PlantUML server returned HTTP Error.
    """

    def __init__(self, response, content, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.response = response
        self.content = content

    def __str__(self):
        return str(self.content)


def deflate_and_encode(plantuml_text):
    """zlib compress the plantuml text and encode it for the plantuml server.
    """
    zlibbed_str = compress(plantuml_text.encode('utf-8'))
    compressed_string = zlibbed_str[2:-4]
    return base64.b64encode(compressed_string).translate(b64_to_plantuml).decode('utf-8')


class PlantUML(object):
    """Connection to a PlantUML server with optional authentication.
    
    All parameters are optional.
    
    :param str url: URL to the PlantUML server image CGI. defaults to
                    http://www.plantuml.com/plantuml/img/
    :param dict basic_auth: This is if the plantuml server requires basic HTTP
                    authentication. Dictionary containing two keys, 'username'
                    and 'password', set to appropriate values for basic HTTP
                    authentication.
    :param dict form_auth: This is for plantuml server requires a cookie based
                    webform login authentication. Dictionary containing two
                    primary keys, 'url' and 'body'. The 'url' should point to
                    the login URL for the server, and the 'body' should be a
                    dictionary set to the form elements required for login.
                    The key 'method' will default to 'POST'. The key 'headers'
                    defaults to
                    {'Content-type':'application/x-www-form-urlencoded'}.
                    Example: form_auth={'url': 'http://example.com/login/',
                    'body': { 'username': 'me', 'password': 'secret'}
    :param dict http_opts: Extra options to be passed off to the
                    httplib2.Http() constructor.
    :param dict request_opts: Extra options to be passed off to the
                    httplib2.Http().request() call.
                    
    """

    def __init__(self, url, basic_auth={}, form_auth={},
                 http_opts={}, request_opts={}):
        self.HttpLib2Error = httplib2.HttpLib2Error
        self.url = url
        self.request_opts = request_opts
        self.auth_type = 'basic_auth' if basic_auth else (
            'form_auth' if form_auth else None)
        self.auth = basic_auth if basic_auth else (
            form_auth if form_auth else None)

        self.http = httplib2.Http(**http_opts)

        if self.auth_type == 'basic_auth':
            self.http.add_credentials(
                self.auth['username'], self.auth['password'])
        elif self.auth_type == 'form_auth':
            if 'url' not in self.auth:
                raise ValueError(
                    "The form_auth option 'url' must be provided and point to "
                    "the login url.")
            if 'body' not in self.auth:
                raise ValueError(
                    "The form_auth option 'body' must be provided and include "
                    "a dictionary with the form elements required to log in. "
                    "Example: form_auth={'url': 'http://example.com/login/', "
                    "'body': { 'username': 'me', 'password': 'secret'}")
            login_url = self.auth['url']
            body = self.auth['body']
            method = self.auth.get('method', 'POST')
            headers = self.auth.get(
                'headers', {'Content-type': 'application/x-www-form-urlencoded'})
            try:
                response, content = self.http.request(
                    login_url, method, headers=headers,
                    body=urlencode(body))
            except self.HttpLib2Error as e:
                raise ValueError(e)
            if response.status != 200:
                raise PlantUMLHTTPError(response, content)
            self.request_opts['Cookie'] = response['set-cookie']

    def get_url(self, plantuml_text):
        """Return the server URL for the image.
        You can use this URL in an IMG HTML tag.
        
        :param str plantuml_text: The plantuml markup to render
        :returns: the plantuml server image URL
        """
        return self.url + deflate_and_encode(plantuml_text)

    def processes(self, plantuml_text):
        """Processes the plantuml text into the raw PNG image data.
        
        :param str plantuml_text: The plantuml markup to render
        :returns: the raw image data
        """
        url = self.get_url(plantuml_text)
        try:
            response, content = self.http.request(url, **self.request_opts)
        except self.HttpLib2Error as e:
            raise ValueError(e)
        if response.status == 200:
            return content
        else:
            ascii_url = self.get_url(plantuml_text)
            ascii_url = ascii_url.replace("img", "txt")
            try:
                ascii_response, ascii_content = self.http.request(ascii_url, **self.request_opts)
                raise PlantUMLHTTPError(ascii_response, ascii_content.decode())
            except self.HttpLib2Error as e:
                raise ValueError(e)

class AIPlantUMLGenerator:
    def __init__(self, llm: BaseChatModel, generator: PlantUML) -> None:
        self.llm = llm
        self.generator = generator
    
    def generate_plantuml(self, user_prompt: str, errors: str) -> str:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """You are an AI designed to help make uml diagrams. 
You will write plantuml code according to the user requirements.
Generating invalid code will result in fatal error so be careful.
Using complex syntax has higher chance of error so keep it simple.
You must only output the code no useless text(important)
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """Here are the user requirements:
===========
{requirements}
============

Last time your code caused these errors so avoid them:
===========
{errors}
===========

If the requirements dont make sense, generate a random diagram
Think step by step (Failure causes big error)
The plantuml code, nothing else:"""
                ),
            ],
            input_variables=[
                "requirements",
                "errors"
            ],
        )
        chain = LLMChain(prompt=prompt, llm=self.llm)
        return chain.run(requirements=user_prompt, errors=errors)
        
    def run(self, prompt: str) -> bytes:
        errors = []
        for _ in range(3):
            try:
                if not errors:
                    error_message = "There were no errors, well done!"
                else:
                    error_message = "\n".join(errors)
                code = self.generate_plantuml(prompt, errors=error_message)
                data = self.generator.processes(code)
                return data
            except Exception as e:
                string_exception = str(e)
                logging.error(f"Error in uml maker: {e}")
                errors.append(string_exception)
        raise ValueError("Requirements too difficult for AI")

if __name__ == "__main__":
    from langchain.chat_models import ChatOpenAI
    import langchain
    
    langchain.verbose = True
    server = PlantUML(url='http://localhost:8080/img/')
    gen = AIPlantUMLGenerator(
        ChatOpenAI(temperature=0),
        server
    )
    print(gen.run(""""Gimme wrong plantuml"""))

