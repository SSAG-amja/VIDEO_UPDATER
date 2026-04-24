class DiffCalculator:
    @staticmethod
    def get_delta(db_set: set, api_set: set) -> tuple[list, list]:
        """
        두 집합을 비교하여 추가할 항목과 삭제할 항목을 반환합니다.
        - db_set: 현재 DB에 존재하는 매핑 튜플 집합
        - api_set: TMDB API에서 가져온 최신 매핑 튜플 집합
        
        return: (to_add_list, to_delete_list)
        """
        to_add = list(api_set - db_set)
        to_delete = list(db_set - api_set)
        
        return to_add, to_delete