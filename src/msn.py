import sys
import math
import random
import numpy as np
from scipy.spatial import KDTree

class MSTAScorer:
	def __init__(self):
		self.three2one = { 'ALA':'A', 'VAL':'V', 'PHE':'F', 'PRO':'P', 'MET':'M',
					'ILE':'I', 'LEU':'L', 'ASP':'D', 'GLU':'E', 'LYS':'K',
					'ARG':'R', 'SER':'S', 'THR':'T', 'TYR':'Y', 'HIS':'H',
					'CYS':'C', 'ASN':'N', 'GLN':'Q', 'TRP':'W', 'GLY':'G',
					'MSE':'M' } # MSE translated to M, other special codes ignored
		self.symmetry = "first"
		self.R0 = 15
		self.dists = [ 0.5, 1, 2, 4 ]

	def read_pdb(self, fn):
		seq = ""
		xs = []
		ys = []
		zs = []
		ks = []
		index = 0
		for line in open(fn):
			if line.startswith("END"):
				break
			if line.startswith("TER "):
				index = index + 1
				continue	
			name = line[12:16].strip()
			if not name == "CA":
				continue
			alt_loc = line[16]
			if alt_loc != ' ' and alt_loc != 'A':
				continue
			three = line[17:20]
			try:
				one = self.three2one[three]
			except:
				continue
			try:
				x = float(line[30:38])
				y = float(line[38:46])
				z = float(line[47:54])
			except:
				continue
		
			seq += one
			xs.append(x)
			ys.append(y)
			zs.append(z)
			ks.append(index)
		xyz = np.column_stack((np.array(xs), np.array(ys), np.array(zs)))
		tree = KDTree(xyz)

		return seq, xs, ys, zs, xyz, tree, ks

	def msa_col(self, col_nr):
		col_str = ""
		for label in self.labels:
			row = self.msa[label]
			col_str += row[col_nr]
		return col_str

	def read_msa(self, fn):
		sys.stderr.write("\n");
		self.msa = {}
		self.labels = []
		label = None
		seq = ""
		for line in open(fn):
			line = line.strip()
			if len(line) == 0:
				continue
			if line[0] == ">":
				if len(seq) > 0:
					self.labels.append(label)
					self.msa[label] = seq.upper()
				label = line[1:]
				seq = ""
			else:
				seq += line.replace(" ", "")
		if len(seq) > 0:
			self.labels.append(label)
			self.msa[label] = seq.upper()
		self.nr_seqs = len(self.labels)
		if self.nr_seqs == 0:
			sys.stderr.write("\n=== ERROR=== empty MSA\n\n")
			sys.exit(1)
		self.nr_cols = len(self.msa[self.labels[0]])
		for i in range(1, self.nr_seqs):
			if len(self.msa[self.labels[i]]) != self.nr_cols:
				sys.stderr.write("\n=== ERROR=== FASTA is not aligned\n\n")
				sys.exit(1)

	def dali_Z_from_score_and_lengths(self, score, len1, len2):
		n12 = math.sqrt(len1*len2)
		x = min(n12, 400)
		mean = 7.9494 + 0.70852*x + 2.5895e-4*x*x - 1.9156e-6*x*x*x
		if n12 > 400:
			mean += n12 - 400
		sigma = 0.5*mean
		Z = (score - mean) / max(1.0, sigma)
		return Z

	# def align_pair(self, row1, row2):
	# 	pos1 = 0
	# 	pos2 = 0
	# 	pos1s = []
	# 	pos2s = []
	# 	for col in range(self.nr_cols):
	# 		c1 = row1[col]
	# 		c2 = row2[col]
	# 		gap1 = (c1 == '-' or c1 == '.')
	# 		gap2 = (c2 == '-' or c2 == '.')
	# 		if not gap1 and not gap2:
	# 			pos1s.append(pos1)
	# 			pos2s.append(pos2)
	# 		if not gap1:
	# 			pos1 += 1
	# 		if not gap2:
	# 			pos2 += 1
	# 	return pos1s, pos2s

	def get_dist(self, x1, y1, z1, x2, y2, z2):
		dx = x1 - x2
		dy = y1 - y2
		dz = z1 - z2
		d2 = dx*dx + dy*dy + dz*dz
		d = math.sqrt(d2)
		return d

	def get_dist_point(self, p1, p2):
		return np.linalg.norm(p1 -  p2)

	def calc_dist_mx(self, xs, ys, zs):
		n = len(xs)
		mx = []
		for i in range(n):
			mx.append([])
			for j in range(n):
				mx[i].append(0)

		assert len(ys) == n
		assert len(zs) == n
		for i in range(n):
			for j in range(i+1, n):
				d = self.get_dist(xs[i], ys[i], zs[i], xs[j], ys[j], zs[j]);
				mx[i][j] = d
				mx[j][i] = d
		return mx

	def calc_col2pos(self, row):
		col2pos = []
		pos2col = []
		pos = 0
		col = 0
		for c in row:
			if c == '-' or c == '.':
				col2pos.append(None)
			else:
				col2pos.append(pos)
				pos2col.append(col)
				pos += 1
			col += 1
		return col2pos,pos2col

	def read_paths(self, paths_fn):
		paths = []
		for line in open(paths_fn):
			fn = line.strip()
			paths.append(fn)
		return paths

	def read_pdbs_paths(self, paths):
		self.pdb_fns = []
		self.fn2data = {}
		for fn in paths:
			self.pdb_fns.append(fn)
			self.fn2data[fn] = self.read_pdb(fn)
		self.nr_pdbs = len(self.pdb_fns)

	def read_pdbs(self, paths_fn):
		self.read_pdbs_paths(self.read_paths(paths_fn))
	
	def match_seqs_to_pdbs(self):
		self.msai_dx2pdb_idx = []
		self.nr_matched = 0
		self.msa_idxs = []
		self.pdb_idxs = []
		self.matched_pdb_fns = []
		self.not_matched_labels = []
		for msa_idx in range(self.nr_seqs):
			label = self.labels[msa_idx]
			n = len(self.msa[label])
			if n != self.nr_cols:
				sys.stderr.write("\n===ERROR=== Test MSA is not aligned\n")
				sys.exit(1)
			test_row = self.msa[label]
			test_seq = test_row.replace("-", "").replace(".", "").upper()
			matched_pdb_idx = None
			for pdb_idx in range(self.nr_pdbs):
				pdb_fn = self.pdb_fns[pdb_idx]
				if pdb_fn in self.matched_pdb_fns:
					continue
				pdb_seq, _, _, _, _, _, _ = self.fn2data[pdb_fn]
				if pdb_seq.upper() == test_seq:
					matched_pdb_idx = pdb_idx
					self.matched_pdb_fns.append(pdb_fn)
					self.nr_matched += 1
					break
			if matched_pdb_idx is None:
				self.not_matched_labels.append(label)
				continue
			self.msa_idxs.append(msa_idx)
			self.pdb_idxs.append(matched_pdb_idx)
		if self.nr_matched < 2:
			sys.stderr.write("\n===ERROR=== %d/%d sequences matched, must be >=2\n" %
					(self.nr_matched, self.nr_seqs))
			sys.exit(1)

	def set_dist_mxs(self):
		self.dist_mxs = []
		for i in range(self.nr_seqs):
			pdb_idx = self.pdb_idxs[i]
			pdb_fn = self.pdb_fns[pdb_idx]
			pdb_seq, xs, ys, zs, _, _, _ = self.fn2data[pdb_fn]
			self.dist_mxs.append(self.calc_dist_mx(xs, ys, zs))

	def set_col2pos_vec(self):
		self.col2pos_vec = []
		for i in range(self.nr_seqs):
			msa_idx = self.msa_idxs[i]
			label = self.labels[msa_idx]
			row = self.msa[label]
			self.col2pos_vec.append(self.calc_col2pos(row))

	def calc_col_score(self, col):
		total_pair_scores = 0
		nr_seq_pairs = 0
		for seq_idxi in range(self.nr_seqs):
			posi = self.col2pos_vec[seq_idxi][0][col]
			if posi is None:
				continue
			dist_mxi = self.dist_mxs[seq_idxi]
			for seq_idxj in range(seq_idxi+1, self.nr_seqs):
				treej = self.fn2data[self.pdb_idxs[seq_idxj]][5]

				posj = self.col2pos_vec[seq_idxj][0][col]
				if posj is None:
					continue
				nr_seq_pairs += 1
				dist_mxj = self.dist_mxs[seq_idxj]
				pair_score = 0

				nr_pairs = 0
				score = 0
				for col2 in range(self.nr_cols):
					if col2 == col:
						continue
					posi2 = self.col2pos_vec[seq_idxi][0][col2]
					posj2 = self.col2pos_vec[seq_idxj][0][col2]
					if posi2 is None or posj2 is None:
						continue
				
					di = dist_mxi[posi][posi2]
					dj = dist_mxj[posj][posj2]
					if self.symmetry == "first":
						if di > self.R0:
							continue
					elif self.symmetry == "both":
						if di > self.R0 and dj > self.R0:
							continue
					elif self.symmetry == "either":
						if di > self.R0 or dj > self.R0:
							continue

					nr_pairs += 1
					d_l = abs(di - dj)
					score += (int(d_l < 0.5) + int(d_l < 1.0) + int(d_l < 2.0) + int(d_l < 4.0))/4

				if nr_pairs > 0:
					pair_score = score/nr_pairs
					total_pair_scores += pair_score
		if nr_seq_pairs == 0:
			return 0
		return total_pair_scores/nr_seq_pairs
	
	def calc_mean_col_score(self):
		self.total_col_scores = 0
		self.col_scores = []
		for col in range(self.nr_cols):
			col_score = self.calc_col_score(col)
			self.col_scores.append(col_score)
			self.total_col_scores += col_score
		self.mean_col_score = self.total_col_scores/self.nr_cols
		return self.mean_col_score

	def kabsch_algorithm(self, P, Q):
		C = np.dot(np.transpose(P), Q)
		V, S, Wt = np.linalg.svd(C)
		d = (np.linalg.det(V) * np.linalg.det(Wt)) < 0.0
		if d:
			V[:, -1] = -V[:, -1]
		U = np.dot(V, Wt)
		return U


	def calculate_rmsd(self, array1, array2):
		diff = array1 - array2
		squared_diff = np.square(diff)
		mean_squared_diff = np.mean(squared_diff)
		rmsd = np.sqrt(mean_squared_diff)
		return rmsd

	def lddt_score(self, seq1, pos1s, xyz1s, tree1, seq2, pos2s, xyz2s, tree2, kis, kjs ):
		self.nr_cols = len(pos1s[0])
		assert len(pos2s[0]) == self.nr_cols
		L1 = len(xyz1s)
		L2 = len(xyz2s)

		D1 = []
		for i in range(L1):
			D1.append([ None ]*L1)

		D2 = []
		for i in range(L2):
			D2.append([ None ]*L2)
		
		total = 0
		nr_cols_considered = 0

		for coli in range(self.nr_cols):
			pos1i = pos1s[0][coli]
			pos2i = pos2s[0][coli]
			if pos1i is None or pos2i is None:
				print(f"{0.0:5f} ",end="")
				continue
			pos1x = tree1.query_ball_point(xyz1s[pos1i],self.R0)
			pos1c = [pos1s[1][i] for i in pos1x]

			pos1j0 = pos1s[0][coli]
			pos2j0 = pos2s[0][coli]
			k = 0
			for colj in pos1c:
				if coli == colj:
					continue
				pos1j = pos1s[0][colj]
				pos2j = pos2s[0][colj]
				if pos1j is None or pos2j is None:
					continue
#				if kis[pos1i] == kis[pos1j]:
#					continue
				if self.get_dist_point(xyz2s[pos2j], xyz2s[pos2j0]) > self.R0:
					continue
				k = k + 1
			xyz1c = np.zeros((k, 3))
			xyz2c = np.zeros((k, 3)) 
			i = 0
			for colj in pos1c:
				if coli == colj:
					continue
				pos1j = pos1s[0][colj]
				pos2j = pos2s[0][colj]
				if pos1j is None or pos2j is None:
					continue
#				if kis[pos1i] == kis[pos1j]:
#					continue
				if self.get_dist_point(xyz2s[pos2j], xyz2s[pos2j0]) > self.R0:
					continue
				xyz1c[i] = xyz1s[pos1j]-xyz1s[pos1j0]
				xyz2c[i] = xyz2s[pos2j]-xyz2s[pos2j0]
				i = i + 1
			if i > 0:
				rotation_matrix = self.kabsch_algorithm(xyz2c, xyz1c)
				structure2_rotated = np.dot(xyz2c, rotation_matrix)
				rmsd = self.calculate_rmsd(xyz1c,structure2_rotated)
				total += rmsd
#				print(f"{rmsd:5f} ",end="")
				nr_cols_considered += 1
#			else:
#				print(f"{0.0:5f} ",end="")
		print()
		return  total/nr_cols_considered

	def DALI_weight(self, y):
		x = 1.0/(self.D*self.D)
		w = math.exp(-x*y*y)
		return w

	def DALI_dpscorefun(self, d1, d2):
		diff = abs(d1 - d2)
		mean = (d1 + d2)/2
		if mean > 100:
			return 0
		w = self.DALI_weight(mean)
		ratio = diff/mean
		if mean == 0:
			score = w*self.d0
		else:
			score = w*(self.d0 - ratio)
		# print("diff=", diff, "mean=", mean, "w=", w, "ratio=", ratio, "score=", score)
		return score

	def dali_score(self, pos1s, x1s, y1s, z1s, pos2s, x2s, y2s, z2s):
		n = len(pos1s)
		assert len(pos2s) == n
		score = 0
		nr_considered = 0
		for coli in range(n):
			pos1i = pos1s[coli]
			pos2i = pos2s[coli]
			for colj in range(n):
				if colj == coli:
					continue
				pos1j = pos1s[colj]
				pos2j = pos2s[colj]

				dij1 = self.get_dist(
					x1s[pos1i], y1s[pos1i], z1s[pos1i],
					x1s[pos1j], y1s[pos1j], z1s[pos1j])

				dij2 = self.get_dist(
					x2s[pos2i], y2s[pos2i], z2s[pos2i],
					x2s[pos2j], y2s[pos2j], z2s[pos2j])

				if not self.R0 is None:
					if self.symmetry == "first":
						if dij1 > self.R0:
							continue
					elif self.symmetry == "both":
						if dij1 > self.R0 and dij2 > self.R0:
							continue
					elif self.symmetry == "either":
						if dij1 > self.R0 or dij2 > self.R0:
							continue

				nr_considered += 1
				pos_score = self.DALI_dpscorefun(dij1, dij2)
				# print("PosQi=%d PosQj=%d PosTi=%d PosTj=%d dij_Q=%.3g dij_T=%.3g score=%.3g" %
				# 	(pos1i, pos1j, pos2i, pos2j, dij1, dij2, pos_score))
				score += pos_score

		score += n*self.d0
		return score
	
	def calc_dali_scores(self):
		total_Z = 0
		total_score = 0
		nr_pairs = 0
		self.DALI_label1s = []
		self.DALI_label2s = []
		self.DALI_scores = []
		self.DALI_Zs = []
		for i in range(self.nr_matched):
			msa_idxi = self.msa_idxs[i]
			pdb_idxi = self.pdb_idxs[i]
			labeli = self.labels[msa_idxi]
			rowi = self.msa[labeli]
			pdb_fni = self.pdb_fns[pdb_idxi]
			pdb_seqi, xis, yis, zis, _, _, _ = self.fn2data[pdb_fni]
			Li = len(pdb_seqi)
			for j in range(i+1, self.nr_matched):
				msa_idxj = self.msa_idxs[j]
				pdb_idxj = self.pdb_idxs[j]
				labelj = self.labels[msa_idxj]
				rowj = self.msa[labelj]
				pdb_fnj = self.pdb_fns[pdb_idxj]
				pdb_seqj, xjs, yjs, zjs, _, _, _ = self.fn2data[pdb_fnj]
				Lj = len(pdb_seqj)
				# posis, posjs = self.align_pair(rowi, rowj)
				posis = self.col2pos_vec[msa_idxi][0]
				posjs = self.col2pos_vec[msa_idxj][0]
				score = self.dali_score(posis, xis, yis, zis, posjs, xjs, yjs, zjs)
				Z = self.dali_Z_from_score_and_lengths(score, Li, Lj)
				total_score += score
				total_Z += Z
				nr_pairs += 1
				self.DALI_label1s.append(labeli)
				self.DALI_label2s.append(labelj)
				self.DALI_scores.append(score)
				self.DALI_Zs.append(Z)

		self.mean_DALI_score = total_score/nr_pairs
		self.mean_DALI_Z = total_Z/nr_pairs

	def calc_lddt_scores(self):
		total_LDDT = 0
		nr_pairs = 0
		self.LDDT_label1s = []
		self.LDDT_label2s = []
		self.LDDT_scores = []
		for i in range(self.nr_matched):
			msa_idxi = self.msa_idxs[i]
			pdb_idxi = self.pdb_idxs[i]
			labeli = self.labels[msa_idxi]
			rowi = self.msa[labeli]
			pdb_fni = self.pdb_fns[pdb_idxi]
			pdb_seqi, _, _, _, xyzi , treei, kis = self.fn2data[pdb_fni]
			Li = len(pdb_seqi)
			for j in range(i+1, self.nr_matched):
				msa_idxj = self.msa_idxs[j]
				pdb_idxj = self.pdb_idxs[j]
				labelj = self.labels[msa_idxj]
				rowj = self.msa[labelj]
				pdb_fnj = self.pdb_fns[pdb_idxj]
				pdb_seqj, _, _, _, xyzj , treej, kjs = self.fn2data[pdb_fnj]
				Lj = len(pdb_seqj)
				# posis, posjs = self.align_pair(rowi, rowj)
				posis = self.col2pos_vec[msa_idxi]
				posjs = self.col2pos_vec[msa_idxj]
				score = self.lddt_score(pdb_seqi, posis, xyzi , treei, pdb_seqj, posjs, xyzj, treej, kis, kjs)
				total_LDDT += score
				nr_pairs += 1
				self.LDDT_label1s.append(labeli)
				self.LDDT_label2s.append(labelj)
				self.LDDT_scores.append(score)

		self.mean_LDDT_score = total_LDDT/nr_pairs

def create_scorer(Args):
	scorer = MSTAScorer()

	if hasattr(Args, "radius"):
		scorer.R0 = Args.radius
	if hasattr(Args, "symmetry"):
		scorer.symmetry = Args.symmetry
	if hasattr(Args, "horizon"):
		scorer.D = Args.horizon
	if hasattr(Args, "diagwt"):
		scorer.d0 = Args.diagwt

	scorer.thresholds = []
	if hasattr(Args, "dists"):
		scorer.dists = Args.dists
		flds = Args.dists.split(',')
		for fld in flds:
			try:
				t = float(fld)
			except:
				sys.stderr.write("\n===ERROR=== Invalid distance in --dists argument\n\n")
				sys.exit(1)
			scorer.thresholds.append(t)

	return scorer
