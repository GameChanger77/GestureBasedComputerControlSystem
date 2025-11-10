class Action:
    def __init__(self, osType):
        print("action class initialized")
        self.osType = osType

    def takeAction(self, action, data):
        """
        Takes in a string which is an action to execute on the operating system.
        The data is information that is necessary to complete that action.
        :param action: the action to take (change volume, click, switch mode, etc.)
        :param data: a tuple whose contents depend on the action taken.
        :return: maybe it will return if the action was successful.
        """

        print(f"completed action {action} with data {data}")

