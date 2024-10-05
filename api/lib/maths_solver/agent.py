import logging
import re
from typing import List, Optional, Tuple
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from uuid import UUID
from langchain.agents import Tool
from langchain.agents import AgentExecutor
from .python_exec_client import PythonClient
from langchain.schema import (
    SystemMessage,
    BaseMessage,
    HumanMessage,
    AIMessage,
)
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chat_models.base import BaseChatModel
from langchain.agents import AgentExecutor, create_tool_calling_agent
from typing import Any, Optional
from langchain.agents.agent import AgentExecutor
from langchain.schema.agent import AgentFinish



def split_into_chunks(text, chunk_size):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


class CustomCallback(BaseCallbackHandler):
    def __init__(self, callback, on_end_callback, is_openai: bool) -> None:
        self.callback = callback
        self.on_end_callback = on_end_callback
        super().__init__()
        self.cached = True
        self.is_openai = is_openai

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            self.cached = False
        if not self.cached and self.is_openai:
            self.callback(token)

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self.callback(
            "*AI is using a tool to perform calculations to better assist you...*\n"
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when tool ends running."""
        self.callback("\n*AI has finished using the tool and will respond shortly...*\n")

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        print("Agent end", finish, self.cached)
        self.on_end_callback(finish.return_values.get("output", ""))
        if self.cached or not self.is_openai:
            self.callback(finish.return_values.get("output", ""))
        self.callback("@@END@@")
        



class MathSolver:
    def __init__(
        self, python_client: PythonClient, llm: BaseChatModel, is_openai_functions: bool = True, extra_tools: list[Tool] = []
    ) -> None:
        self.python_client = python_client
        self.llm = llm
        self.is_openai_functions = is_openai_functions
        self.python_count = 0
        self.extra_tools = extra_tools

    def make_tools(self) -> list[Tool]:
        try:
            libraries = self.python_client.get_available_libraries()["libraries"]
        except Exception:
            libraries = []

        description = f"""
Used to execute multiline python code wont persist states so run everything once.
        """

        def extract_python_code(text: str) -> List[str]:
            """
            Extract Python code blocks from a given text.

            Parameters:
                text (str): The input text containing Python code blocks.

            Returns:
                List[str]: A list of Python code blocks.
            """
            # Regular expression to match Python code blocks enclosed in triple backticks
            pattern = r"```python\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            joined_matches = "\n".join(matches)
            return joined_matches or text.strip()

        def python_function(code: str):
            logging.info(f"Runing {code}")
            max_count = 3 if self.is_openai_functions else 2
            if self.python_count >= max_count:
                return "Cannot use tool anymore, just answer what you know"
            result = self.python_client.evaluate_code(extract_python_code(code))
            self.python_count += 1
            try:
                return result["result"]
            except Exception as e:
                return result

        return [Tool("python", python_function, description), *self.extra_tools]

    def make_agent(
        self, llm: BaseChatModel
    ) -> AgentExecutor:
        system_prompt = """
You are an AI designed to assist students by solving problems with a set of tools. Your responses should include:

1. The answer to the user's question in markdown format.
2. A clear explanation of the answer, including definitions, assumptions, intermediate results, units, and the problem statement. Use simple language suitable for someone without a technical background.
3. A detailed, step-by-step guide on how the student can solve the same question by hand, as they will not have access to any tools.
4. Ensure all instructions are in English and easy to understand, including any necessary mathematical steps. Specify any rules or formulas used.
5. Use LaTeX for any mathematical equations and symbols.
6. Do not provide code, as the user is not technical. But run python tool to get to the answers.
7. YOu must use python for getting the answer.


Remember to explain thoroughly in English, as the student will be solving the problem on paper without any digital tools.
        """

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=system_prompt),
                MessagesPlaceholder(variable_name='chat_history'),
                MessagesPlaceholder(variable_name='input'),
                MessagesPlaceholder(variable_name='agent_scratchpad')
            ]
        )


        tools = self.make_tools()
        agent_obj = create_tool_calling_agent(llm, tools, prompt)
        return AgentExecutor.from_agent_and_tools(
            agent=agent_obj,
            tools=tools,
            handle_parsing_errors=True,
            max_iterations=5,
        )



    def wrap_prompt(self, prompt: str) -> str:
        return f"""{prompt}. [Remember to get to the answer using tools]"""

    def run_agent(
        self,
        prompt: str,
        callback: callable = None,
        on_end_callback: callable = None,
        chat_history: list[tuple[str, str]] = None,
    ):
        if chat_history is None:
            chat_history = []

        agent = self.make_agent(
            llm=self.llm,
        )
       
        return agent.invoke(
            {
                "input": [HumanMessage(content=self.wrap_prompt(prompt))],
                "chat_history" : self.format_messages(chat_history, 2000, self.llm)
            },
            config={
                "callbacks" : [CustomCallback(callback, on_end_callback, self.is_openai_functions)]
            }
        )


    def format_messages(
        self,
        chat_history: List[Tuple[str, str]],
        tokens_limit: int,
        llm: BaseChatModel,
    ) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        tokens_used: int = 0

        for human_msg, ai_msg in reversed(chat_history):
            human_tokens = len(human_msg)
            ai_tokens = len(ai_msg)
            if tokens_used + ai_tokens <= tokens_limit:
                messages.append(AIMessage(content=ai_msg))
                tokens_used += ai_tokens

            # Add the human message if it doesn't exceed the limit.
            if tokens_used + human_tokens <= tokens_limit:
                messages.append(HumanMessage(content=human_msg))
                tokens_used += human_tokens
            else:
                break  # If we can't add a human message, we have reached the token limit.

        return list(reversed(messages))
