import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import CollationDB, DomainError

class CollationFlowTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=CollationDB(self.path)
        self.owner=self.db.add_user("负责人","owner"); self.editor=self.db.add_user("编辑","editor"); self.reviewer=self.db.add_user("审阅","reviewer"); self.outsider=self.db.add_user("外部","reviewer")
        self.work=self.db.create_work("残卷","异文比较",self.owner)
        self.w1=self.db.add_witness(self.work,"甲本","version"); self.w2=self.db.add_witness(self.work,"乙本","fragment","馆藏残片","中段缺页")
        self.db.grant_witness_editor(self.w2,self.editor,self.owner); self.db.grant_work_access(self.work,self.reviewer,"view",self.owner)
        self.passage=self.db.add_passage(self.work,"第一节","春水东流，故人南去。",self.owner)
        self.db.align_passage(self.passage,self.w1,"春水东流，故人南去。",1,self.owner)
        self.db.align_passage(self.passage,self.w2,"春水东流，[缺页]",2,self.editor)
    def tearDown(self): self.db.close(); os.unlink(self.path)
    def test_multilayer_revision_snapshot_export_and_lock(self):
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        rev=self.db.update_variant(variant,"春水东流，[不可辨]人南去。","墨迹受损，不再直接补写",self.editor,1)
        self.assertEqual(2,rev)
        snap=self.db.get_snapshot(self.passage,2,self.owner)
        self.assertEqual(2,snap["layer"])
        exported=self.db.export_collation(self.work,self.reviewer)
        self.assertEqual(1,exported["gap_count"])
        self.assertTrue(exported["passages"][0]["variants"][0]["notes"] == [])
        self.db.lock_passage(self.passage,self.owner,"定稿")
        with self.assertRaisesRegex(DomainError,"锁定"):
            self.db.update_variant(variant,"另一文本","无意义修改",self.editor,2)
    def test_optimistic_lock_permission_and_mark_validation(self):
        first=self.db.create_variant(self.passage,self.w2,"补足一","理由一",self.editor,0)
        with self.assertRaisesRegex(DomainError,"版本冲突"):
            self.db.create_variant(self.passage,self.w2,"补足二","理由二",self.editor,0)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.create_variant(self.passage,self.w2,"补足三","理由三",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.export_collation(self.work,self.outsider)
        with self.assertRaisesRegex(DomainError,"括号"):
            self.db.align_passage(self.passage,self.w1,"文本[未闭合",9,self.owner)

class RulingFlowTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=CollationDB(self.path)
        self.owner=self.db.add_user("负责人","owner"); self.editor=self.db.add_user("编辑","editor")
        self.reviewer=self.db.add_user("审阅","reviewer"); self.viewer=self.db.add_user("旁观","reviewer"); self.outsider=self.db.add_user("外部","reviewer")
        self.work=self.db.create_work("残卷","裁定流程",self.owner)
        self.w1=self.db.add_witness(self.work,"甲本","version"); self.w2=self.db.add_witness(self.work,"乙本","fragment","馆藏残片","中段缺页")
        self.db.grant_witness_editor(self.w2,self.editor,self.owner)
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner); self.db.grant_work_access(self.work,self.viewer,"view",self.owner)
        self.passage=self.db.add_passage(self.work,"第一节","春水东流，故人南去。",self.owner)
        self.db.align_passage(self.passage,self.w1,"春水东流，故人南去。",1,self.owner)
        self.db.align_passage(self.passage,self.w2,"春水东流，[缺页]",2,self.editor)
    def tearDown(self): self.db.close(); os.unlink(self.path)
    def test_ruling_pending_confirm_rerule_and_export(self):
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按甲本补足",self.editor,0)
        rid,status=self.db.create_ruling(self.passage,variant,"甲乙互补，采用补足文本",self.reviewer)
        self.assertEqual("confirmed",status)
        exported=self.db.export_collation(self.work,self.reviewer)
        self.assertEqual("春水东流，故人南去。",exported["passages"][0]["ruling"]["adopted_text"])
        self.assertEqual(0,exported["pending_ruling_count"]); self.assertEqual(0,exported["history_ruling_count"])
        self.db.update_variant(variant,"春水东流，[残损]南去。","新出残片显示此处残损",self.editor,1)
        with self.assertRaisesRegex(DomainError,"变更原因"):
            self.db.create_ruling(self.passage,variant,"改采残损文本",self.reviewer)
        rid2,status2=self.db.create_ruling(self.passage,variant,"残片证据更可靠",self.reviewer,"新残片证据")
        self.assertEqual("pending",status2)
        exported=self.db.export_collation(self.work,self.reviewer)
        self.assertEqual(1,exported["pending_ruling_count"]); self.assertEqual(1,exported["history_ruling_count"])
        with self.assertRaisesRegex(DomainError,"负责人"):
            self.db.confirm_ruling(rid2,self.reviewer)
        self.db.confirm_ruling(rid2,self.owner)
        exported=self.db.export_collation(self.work,self.owner)
        passage=exported["passages"][0]
        self.assertEqual("confirmed",passage["ruling"]["status"])
        self.assertEqual("春水东流，[残损]南去。",passage["ruling"]["adopted_text"])
        self.assertEqual(0,exported["pending_ruling_count"]); self.assertEqual(1,exported["history_ruling_count"])
        self.assertEqual("superseded",passage["ruling_history"][0]["status"])
        self.assertEqual("新残片证据",passage["ruling_history"][0]["change_reason"])
    def test_ruling_permission_and_validation(self):
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按甲本补足",self.editor,0)
        with self.assertRaisesRegex(DomainError,"审阅"):
            self.db.create_ruling(self.passage,variant,"采纳甲本文本",self.viewer)
        with self.assertRaisesRegex(DomainError,"审阅"):
            self.db.create_ruling(self.passage,variant,"采纳甲本文本",self.outsider)
        with self.assertRaisesRegex(DomainError,"取舍说明"):
            self.db.create_ruling(self.passage,variant,"好",self.reviewer)
        with self.assertRaisesRegex(DomainError,"不属于"):
            self.db.create_ruling(self.passage,999,"采纳甲本文本",self.reviewer)
        rid,_=self.db.create_ruling(self.passage,variant,"采纳甲本文本",self.reviewer)
        with self.assertRaisesRegex(DomainError,"待确认"):
            self.db.confirm_ruling(rid,self.owner)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.list_rulings(self.passage,self.outsider)
        self.assertEqual(1,len(self.db.list_rulings(self.passage,self.viewer)["rulings"]))

if __name__=="__main__": unittest.main()
