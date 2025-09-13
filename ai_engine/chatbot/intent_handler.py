from ai_engine.chatbot.chatbot_flow import ChatbotFlow

class IntentHandler:
    def __init__(self):
        self.chatbot_flow = ChatbotFlow()

    def handle_message(self, message):
        return self.chatbot_flow.handle_input(message)

    def is_analysis_complete(self):
        return self.chatbot_flow.is_analysis_complete()

    def get_report_path(self):
        return self.chatbot_flow.get_report_path()
