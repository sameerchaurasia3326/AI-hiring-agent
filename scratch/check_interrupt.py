try:
    from langgraph.types import Interrupt
    print("Found Interrupt in langgraph.types")
except ImportError:
    print("Interrupt NOT in langgraph.types")

try:
    from langgraph.errors import GraphInterrupt
    print("Found GraphInterrupt in langgraph.errors")
except ImportError:
    print("GraphInterrupt NOT in langgraph.errors")
