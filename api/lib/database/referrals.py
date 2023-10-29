from .users import UserDBManager
from .points import UserPointsManager

class ReferralManager:
    def __init__(
        self,
        user_db_manager: UserDBManager,
        points_manager: UserPointsManager,
        referral_points: int = 15,
    ) -> None:
        self.user_db_manager = user_db_manager
        self.points_manager = points_manager
        self.referral_points = referral_points

    def apply_referral_code(self, uid: str, referral_code: str) -> None:
        user = self.user_db_manager.get_user_by_uid(uid)
        if not user:
            raise ValueError(f"User with ID {uid} does not exist.")

        if user.referred_by:
            raise ValueError("Referral code has already been applied for this user.")

        if referral_code == uid:
            raise ValueError("You cannot refer yourself.")

        if not self.user_db_manager.user_exists(referral_code):
            raise ValueError("Invalid referral code.")

        # Update the referred_by field for the user
        self.user_db_manager.update_user(uid, referred_by=referral_code)

        # Add points to the referrer
        self.points_manager.increment_user_points(referral_code, self.referral_points)

        self.points_manager.increment_user_points(uid, self.referral_points)
