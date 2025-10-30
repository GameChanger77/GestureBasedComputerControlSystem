
class Strategizer:
    def __init__(self):
        print("Strategizer initialized")

    def strategize(self, hands_data):
        """
        Method called when landmarks are detected
        Override this method to implement your custom logic

        Args:
            detection_result: MediaPipe detection result containing hand landmarks

        :param hands_data: The landmark data for the hands prepared by the get_hands_data method
        :returns a tuple of the action and some information for that data. (action, (data))
        """
        # Get left hand thumb tip (landmark 4 of thumb)
        if 'Left' in hands_data:
            thumb_tip = hands_data['Left'][0][4]  # [0] = thumb, [4] = tip
            print(f"Left thumb tip: {thumb_tip}")

        # Get right hand index finger tip (landmark 4 of index)
        if 'Right' in hands_data:
            index_tip = hands_data['Right'][1][4]  # [1] = index, [4] = tip
            print(f"Right index tip: {index_tip}")

        return "action", ("data", "more data")
