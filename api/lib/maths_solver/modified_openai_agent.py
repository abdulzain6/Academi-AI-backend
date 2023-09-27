from langchain.agents.openai_functions_agent.base import OpenAIFunctionsAgent
import json
from json import JSONDecodeError
from typing import Any, List, Tuple, Union

from langchain.callbacks.manager import Callbacks
from langchain.schema import (
    AgentAction,
    AgentFinish
)
from langchain.schema.messages import (
    AIMessage,
    BaseMessage,
    FunctionMessage,
)
from dataclasses import dataclass
from langchain.schema.agent import AgentActionMessageLog

_FunctionsAgentAction = AgentActionMessageLog

def _create_function_message(
    agent_action: AgentAction, observation: str
) -> FunctionMessage:
    """Convert agent action and observation into a function message.
    Args:
        agent_action: the tool invocation request from the agent
        observation: the result of the tool invocation
    Returns:
        FunctionMessage that corresponds to the original tool invocation
    """
    if not isinstance(observation, str):
        try:
            content = json.dumps(observation, ensure_ascii=False)
        except Exception:
            content = observation
    else:
        content = observation
    return FunctionMessage(
        name=agent_action.tool,
        content=content,
    )
    
def _convert_agent_action_to_messages(
    agent_action: AgentAction, observation: str
) -> List[BaseMessage]:
    """Convert an agent action to a message.

    This code is used to reconstruct the original AI message from the agent action.

    Args:
        agent_action: Agent action to convert.

    Returns:
        AIMessage that corresponds to the original tool invocation.
    """
    if isinstance(agent_action, _FunctionsAgentAction):
        return agent_action.message_log + [
            _create_function_message(agent_action, observation)
        ]
    else:
        return [AIMessage(content=agent_action.log)]
    
def _format_intermediate_steps(
    intermediate_steps: List[Tuple[AgentAction, str]],
) -> List[BaseMessage]:
    """Format intermediate steps.
    Args:
        intermediate_steps: Steps the LLM has taken to date, along with observations
    Returns:
        list of messages to send to the LLM for the next prediction
    """
    messages = []

    for intermediate_step in intermediate_steps:
        agent_action, observation = intermediate_step
        messages.extend(_convert_agent_action_to_messages(agent_action, observation))

    return messages

def _parse_ai_message(message: BaseMessage) -> Union[AgentAction, AgentFinish]:
    """Parse an AI message."""
    if not isinstance(message, AIMessage):
        raise TypeError(f"Expected an AI message got {type(message)}")

    if function_call := message.additional_kwargs.get("function_call", {}):
        return make_action(function_call, message)
    return AgentFinish(return_values={"output": message.content}, log=message.content)

def make_action(function_call, message):
    function_name = function_call["name"]
    try:
        _tool_input = json.loads(function_call["arguments"])
    except JSONDecodeError:
        _tool_input = {"__arg1" : function_call["arguments"]}

    tool_input = _tool_input.get("__arg1", _tool_input)
    content_msg = "responded: {content}\n" if message.content else "\n"

    return _FunctionsAgentAction(
        tool=function_name,
        tool_input=tool_input,
        log=f"\nInvoking: `{function_name}` with `{tool_input}`\n{content_msg}\n",
        message_log=[message],
    )

class ModifiedOpenAIAgent(OpenAIFunctionsAgent):
    def plan(
        self,
        intermediate_steps: List[Tuple[AgentAction, str]],
        callbacks: Callbacks = None,
        with_functions: bool = True,
        **kwargs: Any,
    ) -> Union[AgentAction, AgentFinish]:
        """Given input, decided what to do.

        Args:
            intermediate_steps: Steps the LLM has taken to date, along with observations
            **kwargs: User inputs.

        Returns:
            Action specifying what tool to use.
        """
        agent_scratchpad = _format_intermediate_steps(intermediate_steps)
        selected_inputs = {
            k: kwargs[k] for k in self.prompt.input_variables if k != "agent_scratchpad"
        }
        full_inputs = dict(**selected_inputs, agent_scratchpad=agent_scratchpad)
        prompt = self.prompt.format_prompt(**full_inputs)
        messages = prompt.to_messages()
        if with_functions:
            predicted_message = self.llm.predict_messages(
                messages,
                functions=self.functions,
                callbacks=callbacks,
            )
        else:
            predicted_message = self.llm.predict_messages(
                messages,
                callbacks=callbacks,
            )
        return _parse_ai_message(predicted_message)